"""
services.chat_jobs — Chat job tracking: state, executors, lifecycle helpers.

Extracted from services/__init__.py as part of Phase B.
All symbols here are re-exported via services/__init__.py so that existing
callers (via `from services import *`) continue to work unchanged.
"""
import re
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
        'response': job.get('response', ''),
        'stage_trace': job.get('stage_trace') or [],
    }
