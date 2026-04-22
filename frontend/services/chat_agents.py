"""chat_agents.py — Ollama / local-agent helpers used by the chat engine.

Extracted from frontend/blueprints/chat.py during Session 25 Step 4.

NOTE: `_chat_try_hard_kill_local_agent` deliberately stays in chat.py —
it collides by name with the worker-pool variant in services.chat_jobs,
and chat.py historically shadows that one with a CLI-based variant.

LINKED TO:
  frontend/blueprints/chat.py — consumes these through `from services import *`.
  services/__init__.py        — re-exports every name below.
  core/llm.py                 — sole gateway for ollama.ps().
"""
from core import llm as _llm

from .chat_jobs import _normalize_chat_participant


def _local_ollama_chat_agents():
    """Single-task local Ollama agents eligible for hard-kill via `ollama stop`.
    Computed from the DB registry (tier=local minus shared-memory runners)."""
    try:
        from utils.db.registry import get_single_task_locals
        return get_single_task_locals()
    except Exception:
        # Registry unavailable — fail closed: no hard-kill on unknown agents.
        return set()


def _chat_model_aliases(name):
    raw = str(name or '').strip().lower()
    if not raw:
        return set()
    aliases = {raw}
    if ':' in raw:
        aliases.add(raw.split(':', 1)[0])
    return aliases


def _chat_agent_configured_model(agent_name):
    normalized = _normalize_chat_participant(agent_name)
    if not normalized:
        return ''
    try:
        from utils.db.registry import get_all_agents_raw
        roster = get_all_agents_raw() or []
    except Exception:
        return ''
    for row in roster:
        name = _normalize_chat_participant(row.get('name'))
        if name == normalized:
            return str(row.get('model') or '').strip()
    return ''


def _chat_running_ollama_models():
    try:
        running = _llm.ps()
        models = list(running.models if hasattr(running, 'models') else [])
        names = []
        for model in models:
            name = str(getattr(model, 'model', '') or getattr(model, 'name', '') or '').strip()
            if name:
                names.append(name)
        return names
    except Exception:
        return []


__all__ = [
    '_chat_agent_configured_model',
    '_chat_model_aliases',
    '_chat_running_ollama_models',
    '_local_ollama_chat_agents',
]
"""chat_agents.py — Ollama / local-agent helpers used by the chat engine.

Extracted from frontend/blueprints/chat.py during Session 25 Step 4.
These helpers resolve configured Ollama models for an agent name and
implement the chat-scoped hard-kill path via `ollama stop`.

Note: services.chat_jobs owns a separate `_chat_try_hard_kill_local_agent`
geared at worker-pool lifecycle. The variant here is the chat-engine one that
actually shells out to the Ollama CLI. Both coexist; call-sites choose.

LINKED TO:
  frontend/blueprints/chat.py — consumes these through `from services import *`.
  services/__init__.py        — re-exports every name below.
  core/llm.py                 — sole gateway for ollama.ps().
"""
import subprocess

from core import llm as _llm

from .chat_jobs import _normalize_chat_participant


def _local_ollama_chat_agents():
    """Single-task local Ollama agents eligible for hard-kill via `ollama stop`.
    Computed from the DB registry (tier=local minus shared-memory runners)."""
    try:
        from utils.db.registry import get_single_task_locals
        return get_single_task_locals()
    except Exception:
        # Registry unavailable — fail closed: no hard-kill on unknown agents.
        return set()


def _chat_model_aliases(name):
    raw = str(name or '').strip().lower()
    if not raw:
        return set()
    aliases = {raw}
    if ':' in raw:
        aliases.add(raw.split(':', 1)[0])
    return aliases


def _chat_agent_configured_model(agent_name):
    normalized = _normalize_chat_participant(agent_name)
    if not normalized:
        return ''
    try:
        from utils.db.registry import get_all_agents_raw
        roster = get_all_agents_raw() or []
    except Exception:
        return ''
    for row in roster:
        name = _normalize_chat_participant(row.get('name'))
        if name == normalized:
            return str(row.get('model') or '').strip()
    return ''


def _chat_running_ollama_models():
    try:
        running = _llm.ps()
        models = list(running.models if hasattr(running, 'models') else [])
        names = []
        for model in models:
            name = str(getattr(model, 'model', '') or getattr(model, 'name', '') or '').strip()
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _chat_try_hard_kill_local_agent(agent_name):
    normalized = _normalize_chat_participant(agent_name)
    result = {
        'agent': normalized or str(agent_name or '').strip().lower(),
        'configured_model': '',
        'models': [],
        'attempts': [],
        'ok': False,
        'detail': '',
    }
    if normalized not in _local_ollama_chat_agents():
        result['detail'] = 'agent is not an Ollama-backed local runtime'
        return result

    configured_model = _chat_agent_configured_model(normalized)
    result['configured_model'] = configured_model
    wanted_aliases = _chat_model_aliases(configured_model)
    running_models = _chat_running_ollama_models()

    candidates = []
    for running_name in running_models:
        if wanted_aliases and _chat_model_aliases(running_name) & wanted_aliases:
            candidates.append(running_name)
    if configured_model and not candidates:
        candidates.append(configured_model)
    if not candidates:
        result['detail'] = 'no matching Ollama model is configured or currently running'
        return result

    unique_candidates = []
    seen = set()
    for model_name in candidates:
        key = str(model_name or '').strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_candidates.append(str(model_name).strip())

    result['models'] = unique_candidates
    for model_name in unique_candidates:
        try:
            proc = subprocess.run(
                ['ollama', 'stop', model_name],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            stdout = str(proc.stdout or '').strip()
            stderr = str(proc.stderr or '').strip()
            ok = proc.returncode == 0
            result['attempts'].append({
                'model': model_name,
                'ok': ok,
                'returncode': proc.returncode,
                'stdout': stdout,
                'stderr': stderr,
            })
        except Exception as exc:
            result['attempts'].append({
                'model': model_name,
                'ok': False,
                'returncode': None,
                'stdout': '',
                'stderr': str(exc),
            })

    ok_models = [item['model'] for item in result['attempts'] if item.get('ok')]
    result['ok'] = bool(ok_models)
    if ok_models:
        result['detail'] = 'stopped ' + ', '.join(ok_models)
    else:
        errors = [item.get('stderr') or item.get('stdout') or 'unknown error' for item in result['attempts']]
        result['detail'] = '; '.join(errors[:2])
    return result


__all__ = [
    '_chat_agent_configured_model',
    '_chat_model_aliases',
    '_chat_running_ollama_models',
    '_chat_try_hard_kill_local_agent_via_cli',
    '_local_ollama_chat_agents',
]

# Public alias — chat.py historically called this `_chat_try_hard_kill_local_agent`,
# and services.chat_jobs ALSO exports a function of the same name that does the
# worker-pool side. To avoid a naming collision in `services/__init__.py`, the
# CLI variant is re-exported under an explicit alias below.
_chat_try_hard_kill_local_agent_via_cli = _chat_try_hard_kill_local_agent
