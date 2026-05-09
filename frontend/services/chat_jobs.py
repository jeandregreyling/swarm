"""
services.chat_jobs — Chat job tracking: state, executors, lifecycle helpers.

Extracted from services/__init__.py as part of Phase B.
All symbols here are re-exported via services/__init__.py so that existing
callers (via `from services import *`) continue to work unchanged.
"""
import re
import os
import json
import time
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from utils.db.registry import (
    get_agent_aliases     as _reg_aliases,
    get_agent_etas        as _reg_etas,
    get_agent_runtime_classes as _reg_runtime,
    get_agent_models      as _reg_models,
)


# ── Persistent chat jobs (timeout-safe) ───────────────────────────────────────
_CHAT_JOB_LOCK = threading.Lock()
_CHAT_JOBS = {}
_CHAT_JOB_TTL_SECONDS = 2 * 60 * 60

# Watchdog: Thread #2104 (Gemma) hung for 12+ minutes in April 2026. Any job
# still 'running' with no fresh progress past max(ETA × WATCHDOG_ETA_MULT,
# WATCHDOG_MIN_SECONDS) is marked failed with a user-visible stall reason so
# the chat surface doesn't freeze behind a thinking bubble forever. Total
# runtime alone is not a stall; streamed progress updates keep the job alive.
_CHAT_WATCHDOG_ETA_MULT = 4.0
_CHAT_WATCHDOG_MIN_SECONDS = 300   # 5 min floor even for fast agents
_CHAT_WATCHDOG_MAX_SECONDS = int(os.environ.get('SWARM_CHAT_HANDOFF_DEADLINE_SECONDS') or 2000)  # Ghost-visible handoff deadline ceiling
_CHAT_WATCHDOG_LOCAL_GRACE_SECONDS = 120

# Ring buffer of recently finished jobs (per agent) for health metrics.
# Newest first; capped to the last _CHAT_HEALTH_RING_MAX entries per agent.
_CHAT_HEALTH_RING = {}
_CHAT_HEALTH_RING_MAX = 50

# ── Shared thread pools for chat dispatch ─────────────────────────────────────
# Two separate pools to prevent deadlock from nested submits:
#   _CHAT_DISPATCH_EXECUTOR  — outer layer: api_chat submits _run_single_agent here
#   _CHAT_WORKER_EXECUTOR    — inner layer: _run_single_agent submits agent calls here
_CHAT_DISPATCH_EXECUTOR = ThreadPoolExecutor(max_workers=12, thread_name_prefix='chat-dispatch')
_CHAT_WORKER_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix='chat-worker')


def _chat_now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _chat_eta_seconds(agent):
    return int(_reg_etas().get((agent or '').lower(), 60))


def _chat_runtime_class(agent):
    return _reg_runtime().get((agent or '').lower(), 'unknown')


def _normalize_chat_participant(name):
    raw = str(name or '').strip().lower()
    if not raw:
        return ''
    aliases = _reg_aliases()
    squashed = re.sub(r'[^a-z0-9]+', '', raw)
    return aliases.get(squashed, aliases.get(raw, raw))


def _chat_stage_for(agent, elapsed_ms):
    elapsed = max(0, int(elapsed_ms or 0))
    if agent == 'gemma':
        if elapsed < 8000:
            return 'assembling context'
        if elapsed < 22000:
            return 'reasoning/debating'
        if elapsed < 45000:
            return 'synthesizing response'
        return 'finalizing answer'
    if agent in {'duck', 'sniffles'}:
        if elapsed < 4000:
            return 'assembling audit context'
        if elapsed < 16000:
            return 'reviewing evidence'
        return 'writing findings'
    if agent in {'llama', 'mistral', 'qwen', 'eight', 'librarian'}:
        if elapsed < 4000:
            return 'loading local memory'
        if elapsed < 16000:
            return 'processing thread hand-off'
        return 'drafting response'
    if elapsed < 6000:
        return 'loading context'
    if elapsed < 18000:
        return 'reasoning'
    return 'finalizing answer'


def _chat_update_job(job_id, *, stage=None, status=None, eta_seconds=None, error=None):
    if not job_id:
        return
    with _CHAT_JOB_LOCK:
        job = _CHAT_JOBS.get(job_id)
        if not job:
            return
        now_ts = time.time()
        now_iso = _chat_now_iso()
        if stage is not None:
            job['stage'] = str(stage)
            job.setdefault('stage_trace', []).append({'text': str(stage), 'ts': now_ts})
        if status is not None:
            job['status'] = str(status)
        if eta_seconds is not None:
            try:
                job['eta_seconds'] = max(0, int(eta_seconds))
            except Exception:
                pass
        if error is not None:
            job['error'] = str(error)
        job['updated_ts'] = now_ts
        job['updated_at'] = now_iso
        db_snapshot = dict(job)

    if stage is not None or status is not None or error is not None:
        try:
            from utils.db.chat import update_chat_job_db
            update_chat_job_db(
                job_id,
                status=db_snapshot.get('status') or 'running',
                stage=db_snapshot.get('stage') or '',
                error=db_snapshot.get('error') or '',
                elapsed_ms=max(0, int((float(db_snapshot.get('updated_ts') or now_ts) - float(db_snapshot.get('started_ts') or now_ts)) * 1000)),
                tokens=int(db_snapshot.get('tokens') or 0),
                stage_trace_json=json.dumps(db_snapshot.get('stage_trace') or []),
            )
        except Exception:
            pass


def _cleanup_chat_jobs_locked():
    now = time.time()
    stale = []
    for jid, job in _CHAT_JOBS.items():
        finished = job.get('status') in {'completed', 'failed', 'cancelled'}
        updated = float(job.get('updated_ts') or job.get('started_ts') or now)
        if finished and (now - updated) > _CHAT_JOB_TTL_SECONDS:
            stale.append(jid)
    for jid in stale:
        _CHAT_JOBS.pop(jid, None)


def _watchdog_budget_seconds(job):
    """Per-job timeout ceiling. Scales with agent ETA, clamped to sane bounds.

    Rationale: expected local ETA is ~60s (Gemma), so a 4× multiplier gives a
    4-min soft budget; the 5-min floor protects very fast agents; the
    2000-second cap is the visible handoff ceiling for very slow local runs.
    """
    try:
        eta = float(job.get('eta_seconds') or 60.0)
    except Exception:
        eta = 60.0
    budget = max(eta * _CHAT_WATCHDOG_ETA_MULT, float(_CHAT_WATCHDOG_MIN_SECONDS))
    budget = min(budget, float(_CHAT_WATCHDOG_MAX_SECONDS))
    if str(job.get('runtime_class') or '').lower() == 'local':
        return max(budget, float(_CHAT_WATCHDOG_MAX_SECONDS + _CHAT_WATCHDOG_LOCAL_GRACE_SECONDS))
    return budget


def _watchdog_mark_stalled_jobs_locked():
    """Fail any 'running' job that has exceeded its idle watchdog budget.

    Must be called with _CHAT_JOB_LOCK held. Returns the list of job ids that
    were marked failed so the caller can persist + kill + emit SSE outside the
    lock.
    """
    now = time.time()
    stalled = []
    for jid, job in _CHAT_JOBS.items():
        if str(job.get('status') or '') != 'running':
            continue
        started = float(job.get('started_ts') or now)
        elapsed = now - started
        updated = float(job.get('updated_ts') or started)
        idle = now - updated
        budget = _watchdog_budget_seconds(job)
        if idle <= budget:
            continue
        agent = job.get('agent') or 'agent'
        error_msg = (
            f'Watchdog: {agent} had no progress for {int(idle)}s '
            f'(budget {int(budget)}s, elapsed {int(elapsed)}s). Automatic stall detection.'
        )
        job.update({
            'status': 'failed',
            'stage': 'stalled',
            'error': error_msg,
            'updated_ts': now,
            'updated_at': _chat_now_iso(),
            'stalled': True,
        })
        job.setdefault('stage_trace', []).append({'text': 'stalled (watchdog)', 'ts': now})
        stalled.append({
            'job_id': jid,
            'agent': agent,
            'conversation_id': job.get('conversation_id'),
            'elapsed_ms': int(elapsed * 1000),
            'idle_ms': int(idle * 1000),
            'eta_seconds': int(job.get('eta_seconds') or 0),
            'error': error_msg,
            'stage_trace': list(job.get('stage_trace') or []),
        })
        # Session 29 — spine emit. Best-effort; never break watchdog if spine is absent.
        try:
            from core import spine as _spine
            _spine.log(
                _spine.EventKind.WATCHDOG,
                f'{agent} stalled after {int(elapsed)}s',
                severity=_spine.Severity.WARN,
                source='chat_jobs',
                agent=agent,
                thread_id=str(job.get('conversation_id') or '') or None,
                payload={
                    'job_id': jid,
                    'elapsed_ms': int(elapsed * 1000),
                    'idle_ms': int(idle * 1000),
                    'budget_s': int(budget),
                    'eta_s': int(job.get('eta_seconds') or 0),
                },
            )
        except Exception:
            pass
    return stalled


def _record_job_health_locked(job):
    """Append a finished job's outcome to the per-agent ring buffer.

    Called from the job-completion path and the watchdog path so stalls are
    visible in the health metrics, not hidden.
    """
    agent = str(job.get('agent') or '').strip().lower()
    if not agent:
        return
    started = float(job.get('started_ts') or 0.0)
    updated = float(job.get('updated_ts') or time.time())
    ring = _CHAT_HEALTH_RING.setdefault(agent, [])
    ring.insert(0, {
        'ts': updated,
        'elapsed_ms': max(0, int((updated - started) * 1000)) if started else 0,
        'status': str(job.get('status') or 'unknown'),
        'stalled': bool(job.get('stalled')),
    })
    if len(ring) > _CHAT_HEALTH_RING_MAX:
        del ring[_CHAT_HEALTH_RING_MAX:]


def get_chat_agent_health_snapshot():
    """Public accessor: per-agent p50/p95 and stall counts over the ring.

    Used by /api/chat/agents/health (and, in the future, the Monitor tile).
    Cheap enough to call on every poll.
    """
    snapshot = {}
    with _CHAT_JOB_LOCK:
        for agent, ring in _CHAT_HEALTH_RING.items():
            if not ring:
                continue
            elapsed_ok = sorted(
                r['elapsed_ms'] for r in ring
                if r.get('status') == 'completed' and r.get('elapsed_ms')
            )
            count = len(ring)
            completed = sum(1 for r in ring if r.get('status') == 'completed')
            failed = sum(1 for r in ring if r.get('status') == 'failed')
            stalled = sum(1 for r in ring if r.get('stalled'))

            def _pct(seq, p):
                if not seq:
                    return 0
                k = max(0, min(len(seq) - 1, int(round((p / 100.0) * (len(seq) - 1)))))
                return int(seq[k])

            snapshot[agent] = {
                'count': count,
                'completed': completed,
                'failed': failed,
                'stalled': stalled,
                'p50_ms': _pct(elapsed_ok, 50),
                'p95_ms': _pct(elapsed_ok, 95),
            }
    return snapshot


def _chat_find_running_job_for_agent_locked(agent_name):
    target = str(agent_name or '').strip().lower()
    if not target:
        return None
    for job in _CHAT_JOBS.values():
        if str(job.get('agent') or '').strip().lower() != target:
            continue
        if str(job.get('status') or 'running') == 'running':
            return job
    return None


def _chat_try_hard_kill_local_agent(agent_name):
    """Best-effort hard kill for local Ollama-backed jobs."""
    name = str(agent_name or '').strip().lower()
    if not name:
        return {'agent': name, 'attempted': False, 'ok': False, 'detail': 'missing-agent'}
    if _chat_runtime_class(name) != 'local':
        return {'agent': name, 'attempted': False, 'ok': True, 'detail': 'non-local-agent'}

    model = None
    try:
        model = _reg_models().get(name)
    except Exception:
        model = None

    attempts = []

    if model:
        try:
            import ollama  # type: ignore
            stop_fn = getattr(ollama, 'stop', None)
            if callable(stop_fn):
                try:
                    stop_fn(model)
                    attempts.append(f'ollama.stop({model})')
                    return {'agent': name, 'attempted': True, 'ok': True, 'detail': '; '.join(attempts)}
                except TypeError:
                    stop_fn(model=model)
                    attempts.append(f'ollama.stop(model={model})')
                    return {'agent': name, 'attempted': True, 'ok': True, 'detail': '; '.join(attempts)}
        except Exception as exc:
            attempts.append(f'python-stop-failed:{exc}')

        try:
            import subprocess
            proc = subprocess.run(['ollama', 'stop', str(model)], capture_output=True, text=True, timeout=6)
            if proc.returncode == 0:
                attempts.append(f'cli-stop:{model}')
                return {'agent': name, 'attempted': True, 'ok': True, 'detail': '; '.join(attempts)}
            attempts.append(f'cli-stop-rc:{proc.returncode}')
        except Exception as exc:
            attempts.append(f'cli-stop-failed:{exc}')

    try:
        import subprocess
        # Only kill the specific model runner, not the ollama server
        if model:
            proc = subprocess.run(['pkill', '-f', f'ollama.*run.*{model}'], capture_output=True, text=True, timeout=6)
        else:
            proc = subprocess.run(['pkill', '-f', f'ollama.*run.*{name}'], capture_output=True, text=True, timeout=6)
        attempts.append(f'pkill-model-rc:{proc.returncode}')
        ok = proc.returncode in (0, 1)
        return {'agent': name, 'attempted': True, 'ok': ok, 'detail': '; '.join(attempts)}
    except Exception as exc:
        attempts.append(f'pkill-failed:{exc}')
        return {'agent': name, 'attempted': True, 'ok': False, 'detail': '; '.join(attempts)}


def _chat_job_public(job):
    elapsed_ms = int((time.time() - float(job.get('started_ts') or time.time())) * 1000)
    eta_seconds = int(job.get('eta_seconds') or _chat_eta_seconds(job.get('agent')))
    elapsed_seconds = max(0, int(elapsed_ms / 1000))
    status = job.get('status', 'running')
    if status in {'completed', 'failed', 'cancelled'}:
        eta_remaining_seconds = 0
    else:
        eta_remaining_seconds = max(0, eta_seconds - elapsed_seconds)
    return {
        'job_id': job.get('job_id'),
        'conversation_id': job.get('conversation_id'),
        'agent': job.get('agent'),
        'status': status,
        'runtime_class': job.get('runtime_class') or _chat_runtime_class(job.get('agent')),
        'stage': job.get('stage') or _chat_stage_for(job.get('agent'), elapsed_ms),
        'eta_seconds': eta_seconds,
        'eta_remaining_seconds': eta_remaining_seconds,
        'started_at': job.get('started_at'),
        'updated_at': job.get('updated_at'),
        'elapsed_ms': elapsed_ms,
        'error': job.get('error', ''),
        'stalled': bool(job.get('stalled')),
        'response': job.get('response', ''),
        'stage_trace': job.get('stage_trace') or [],
    }
