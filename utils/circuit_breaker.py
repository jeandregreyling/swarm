"""
utils/circuit_breaker.py — Per-agent circuit breaker + health probe
═══════════════════════════════════════════════════════════════════
Prevents dispatching to repeatedly-failing agents.

States per agent:
  CLOSED   – normal operation (default)
  OPEN     – agent tripped; calls rejected fast for COOLDOWN seconds
  HALF_OPEN – cooldown expired; next call is a probe (one attempt)

Thresholds (env-overridable):
  SWARM_CB_FAIL_THRESHOLD   – failures within the window to trip  (default 3)
  SWARM_CB_WINDOW_SECS      – rolling window for counting failures (default 300)
  SWARM_CB_COOLDOWN_SECS    – how long OPEN lasts before HALF_OPEN (default 60)

Usage:
    from utils.circuit_breaker import check, record_success, record_failure, status

    ok, reason = check('gemma')
    if not ok:
        return reason  # fast-fail, don't dispatch

    try:
        answer = dispatch(...)
        record_success('gemma')
    except Exception as e:
        record_failure('gemma', str(e))
        raise
"""

import os
import threading
import time
import logging
from collections import defaultdict

logger = logging.getLogger('seven.circuit_breaker')

# ── Configuration ───────────────────────────────────────────────────────────

FAIL_THRESHOLD = int(os.environ.get('SWARM_CB_FAIL_THRESHOLD', '3'))
WINDOW_SECS    = int(os.environ.get('SWARM_CB_WINDOW_SECS', '300'))
COOLDOWN_SECS  = int(os.environ.get('SWARM_CB_COOLDOWN_SECS', '60'))

# States
CLOSED    = 'closed'
OPEN      = 'open'
HALF_OPEN = 'half_open'

# ── Per-agent state ─────────────────────────────────────────────────────────

_lock = threading.Lock()

class _AgentBreaker:
    __slots__ = ('state', 'failures', 'opened_at', 'last_error')
    def __init__(self):
        self.state     = CLOSED
        self.failures  = []      # list of timestamps
        self.opened_at = 0.0
        self.last_error = ''

_breakers = defaultdict(_AgentBreaker)   # keyed by agent name


# ── Public API ──────────────────────────────────────────────────────────────

def check(agent_name):
    """Check if agent is dispatchable.

    Returns (ok: bool, reason: str).
    ok=True  → proceed with dispatch
    ok=False → fast-fail, reason has user-facing message
    """
    agent_name = agent_name.lower()
    now = time.time()
    with _lock:
        b = _breakers[agent_name]
        if b.state == CLOSED:
            return True, ''
        if b.state == OPEN:
            elapsed = now - b.opened_at
            if elapsed >= COOLDOWN_SECS:
                b.state = HALF_OPEN
                logger.info(f'[circuit_breaker] {agent_name}: OPEN → HALF_OPEN (cooldown {elapsed:.0f}s)')
                return True, ''   # allow one probe attempt
            remaining = int(COOLDOWN_SECS - elapsed)
            return False, (
                f'[{agent_name}] is temporarily unavailable (circuit open). '
                f'Retry in ~{remaining}s. Last error: {b.last_error}'
            )
        if b.state == HALF_OPEN:
            # Already probing — let through
            return True, ''
    return True, ''


def record_success(agent_name):
    """Record a successful response — resets the breaker to CLOSED."""
    agent_name = agent_name.lower()
    with _lock:
        b = _breakers[agent_name]
        if b.state != CLOSED:
            logger.info(f'[circuit_breaker] {agent_name}: {b.state} → CLOSED (success)')
        b.state = CLOSED
        b.failures.clear()
        b.last_error = ''


def record_failure(agent_name, error_msg=''):
    """Record a failure — may trip the breaker to OPEN."""
    agent_name = agent_name.lower()
    now = time.time()
    with _lock:
        b = _breakers[agent_name]
        if b.state == HALF_OPEN:
            # Probe failed — reopen immediately
            b.state = OPEN
            b.opened_at = now
            b.last_error = str(error_msg)[:300]
            logger.warning(f'[circuit_breaker] {agent_name}: HALF_OPEN → OPEN (probe failed: {error_msg})')
            return

        # Prune old failures outside the window
        cutoff = now - WINDOW_SECS
        b.failures = [t for t in b.failures if t > cutoff]
        b.failures.append(now)
        b.last_error = str(error_msg)[:300]

        if len(b.failures) >= FAIL_THRESHOLD:
            b.state = OPEN
            b.opened_at = now
            logger.warning(
                f'[circuit_breaker] {agent_name}: CLOSED → OPEN '
                f'({len(b.failures)} failures in {WINDOW_SECS}s)'
            )


def reset(agent_name):
    """Manually reset an agent's breaker to CLOSED."""
    agent_name = agent_name.lower()
    with _lock:
        b = _breakers[agent_name]
        b.state = CLOSED
        b.failures.clear()
        b.last_error = ''
        b.opened_at = 0.0
    logger.info(f'[circuit_breaker] {agent_name}: manually reset to CLOSED')


def status():
    """Return dict of all breaker states (for monitoring UI)."""
    now = time.time()
    with _lock:
        out = {}
        for name, b in _breakers.items():
            entry = {
                'state': b.state,
                'recent_failures': len([t for t in b.failures if t > now - WINDOW_SECS]),
                'last_error': b.last_error,
            }
            if b.state == OPEN:
                entry['cooldown_remaining'] = max(0, int(COOLDOWN_SECS - (now - b.opened_at)))
            out[name] = entry
        return out


def status_for(agent_name):
    """Return breaker state for a single agent."""
    agent_name = agent_name.lower()
    now = time.time()
    with _lock:
        b = _breakers[agent_name]
        entry = {
            'state': b.state,
            'recent_failures': len([t for t in b.failures if t > now - WINDOW_SECS]),
            'last_error': b.last_error,
        }
        if b.state == OPEN:
            entry['cooldown_remaining'] = max(0, int(COOLDOWN_SECS - (now - b.opened_at)))
        return entry


# ── Health probe (pre-dispatch) ─────────────────────────────────────────────

_LOCAL_OLLAMA_AGENTS = frozenset({
    'gemma', 'llama', 'qwen', 'eight', 'mistral', 'phi3',
    'deepseek_local', 'duck', 'sniffles', 'librarian',
})

def health_probe(agent_name, timeout=3):
    """Quick pre-dispatch health check.

    For Ollama agents: pings Ollama API.
    For API agents: assumes reachable (API keys validated at import time).
    Returns (healthy: bool, detail: str).
    """
    agent_name = agent_name.lower()
    if agent_name not in _LOCAL_OLLAMA_AGENTS:
        return True, 'api-agent (assumed ok)'
    try:
        from core import llm as _llm
        # Lightweight list call — fast, no model load
        _llm.list_models()
        return True, 'ollama reachable'
    except Exception as e:
        return False, f'ollama unreachable: {e}'
