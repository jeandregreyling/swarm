"""
utils/resource_gate.py — Ollama model resource gate
═══════════════════════════════════════════════════
Enforces a one-model-at-a-time policy for local Ollama inference.

Rules:
  • Eight (gemma4:26b, 17GB) runs exclusively — no other local agent may start
    while Eight is actively running, and Eight will not start while another
    local agent is actively running.
  • All other local models (Mistral, LLaMA, Qwen, Gemma3) queue if another
    local model is actively running, waiting up to QUEUE_WAIT_SECS.
  • Resident warm models reported by Ollama ps() are NOT treated as active
    work by default; keep_alive/prewarm should not block the queue forever.
  • Cloud agents (Nine/Groq, Ten/GPT, Eleven/Grok, Twelve/Claude,
    Scholar, Seeker) are never gated — they do not use local RAM.

Usage:
    from utils.resource_gate import acquire, release, gate_status

    ok, reason = acquire('mistral')
    if not ok:
        raise RuntimeError(reason)
    try:
        ... run model ...
    finally:
        release('mistral')
"""

import os
import threading
import time
import logging

logger = logging.getLogger('seven.resource_gate')

# ── Constants ─────────────────────────────────────────────────────────────────

# Ollama model names mapped to swarm agent names
_AGENT_MODEL_MAP = {
    'gemma':          'gemma3:latest',
    'llama':          'llama3.2:latest',
    'qwen':           'qwen2.5:latest',
    'mistral':        'mistral:latest',
    'eight':          'gemma4:26b',
    'phi3':           'phi3:mini',
    'deepseek_local': 'deepseek-r1:7b',
}

# Eight must run exclusively — nothing else while it is active
_EXCLUSIVE_AGENTS = {'eight'}

# Agents that are NOT local Ollama models — skip the gate entirely
_CLOUD_AGENTS = {'nine', 'ten', 'eleven', 'twelve', 'scholar', 'seeker',
                 'duck', 'sniffles', 'librarian'}

# How long to wait polling for a free slot (seconds)
QUEUE_WAIT_SECS = 300   # 5 minutes max wait
POLL_INTERVAL   = 5     # check every 5 seconds

# ── State ─────────────────────────────────────────────────────────────────────

_lock           = threading.Lock()
_active_agents  = set()   # agents currently running an Ollama model


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ollama_running_models():
    """Return list of model name strings currently loaded in Ollama."""
    try:
        from core import llm as _llm
        result = _llm.ps()
        # result is an object with .models list of RunningModel objects
        models = getattr(result, 'models', None)
        if models is None and isinstance(result, dict):
            models = result.get('models', [])
        if not models:
            return []
        names = []
        for m in models:
            name = getattr(m, 'model', None) or (m.get('model') if isinstance(m, dict) else None)
            if name:
                names.append(str(name))
        return names
    except Exception as e:
        logger.debug(f'[resource_gate] ollama ps error: {e}')
        return []


def _any_exclusive_active():
    """True if Eight (or any exclusive agent) is currently in _active_agents."""
    return bool(_active_agents & _EXCLUSIVE_AGENTS)


def _any_local_active():
    """True if any local Ollama agent is currently in _active_agents."""
    return bool(_active_agents - _CLOUD_AGENTS)


def _check_ollama_conflicts(requesting_agent):
    """
    Check Ollama ps for conflicting running models (catches models started
    outside of this gate, e.g. direct CLI runs).
    Returns (conflict: bool, loaded_model_names: list).
    """
    # Warm resident models are expected because prewarm/keep_alive leave them
    # loaded. They should not be mistaken for active work.
    #
    # If you need the legacy "anything shown by ps() blocks the queue" behavior
    # for debugging or a different machine profile, set:
    #   SWARM_STRICT_OLLAMA_PS_CONFLICTS=1
    if os.environ.get('SWARM_STRICT_OLLAMA_PS_CONFLICTS', '0') != '1':
        return False, _ollama_running_models()

    running = _ollama_running_models()
    if not running:
        return False, []
    return True, running


# ── Public API ─────────────────────────────────────────────────────────────────

def gate_status():
    """Return a dict describing current gate state (for monitoring tile)."""
    with _lock:
        return {
            'active_agents': list(_active_agents),
            'eight_exclusive': _any_exclusive_active(),
            'ollama_loaded': _ollama_running_models(),
        }


def acquire(agent, wait=True):
    """
    Try to acquire a slot for `agent` to run an Ollama model.

    Returns (True, '') on success.
    Returns (False, reason_str) if the agent should not run.

    If wait=True, polls until a slot is free or QUEUE_WAIT_SECS expires.
    """
    if agent in _CLOUD_AGENTS:
        return True, ''   # cloud agents bypass gate

    deadline = time.time() + (QUEUE_WAIT_SECS if wait else 0)
    attempt  = 0

    while True:
        attempt += 1
        with _lock:
            # Eight exclusive: block if another local agent is actively running.
            # Do not treat warm resident models as active work.
            if agent in _EXCLUSIVE_AGENTS and _any_local_active():
                reason = f'Eight exclusive: waiting for active models to finish — {list(_active_agents)}'
            # Non-Eight: block if Eight is active or running
            elif _any_exclusive_active():
                reason = 'Eight is active — no other models may run during an Eight session'
            elif _any_local_active():
                reason = f'Another local model is active: {list(_active_agents - _CLOUD_AGENTS)} — queued'
            else:
                # Also check Ollama ps for models started outside the gate
                conflict, loaded = _check_ollama_conflicts(agent)
                if conflict:
                    reason = f'Ollama has models loaded outside the gate: {loaded} — waiting'
                else:
                    # Clear to go
                    _active_agents.add(agent)
                    logger.info(f'[resource_gate] acquired: {agent} | active={_active_agents}')
                    return True, ''

        # Not acquired — should we wait?
        if time.time() >= deadline:
            logger.warning(f'[resource_gate] {agent} could not acquire slot after {attempt} attempts: {reason}')
            return False, f'[resource gate] system busy — {reason}'

        logger.debug(f'[resource_gate] {agent} waiting ({attempt}) — {reason}')
        time.sleep(POLL_INTERVAL)


def release(agent):
    """Release the slot held by `agent`."""
    if agent in _CLOUD_AGENTS:
        return
    with _lock:
        _active_agents.discard(agent)
    logger.info(f'[resource_gate] released: {agent} | active={_active_agents}')
