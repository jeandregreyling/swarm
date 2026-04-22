"""chat_agents.py — Ollama / local-agent helpers used by the chat engine.

Extracted from frontend/blueprints/chat.py during Session 25 Step 4.

NOTE: `_chat_try_hard_kill_local_agent` deliberately stays in chat.py —
it collides by name with the worker-pool variant in services.chat_jobs,
and chat.py historically shadows that one with a CLI-based variant.
"""
from core import llm as _llm

from .chat_jobs import _normalize_chat_participant


def _local_ollama_chat_agents():
    try:
        from utils.db.registry import get_single_task_locals
        return get_single_task_locals()
    except Exception:
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
