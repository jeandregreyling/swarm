"""
agents/eight/eight_agent.py — Gemma 4 (agent Eight)
Model: gemma4:26b via Ollama.
"""
import logging, sys
from typing import Optional
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/frontend')
logger = logging.getLogger('seven.eight')
AGENT_NAME = 'eight'
MODEL = 'gemma4:26b'


def _resolve_model() -> str:
    """Prefer the DB registry model so runtime and UI stay aligned."""
    try:
        from utils.db.registry import get_agent_models
        configured = str((get_agent_models() or {}).get(AGENT_NAME) or '').strip()
        if configured:
            return configured
    except Exception:
        pass
    return MODEL

def _build_context(message):
    from database import get_connection, get_agent_memory
    lines = ['=== Governance rules (ALM) ===',
             'Mutating changes require approved work proposals.',]
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        lines.append(f'Queue: {queued} queued')
    finally:
        conn.close()
    mems = get_agent_memory(AGENT_NAME, query=message, limit=5)
    if mems:
        lines.append(f"\n=== {AGENT_NAME.capitalize()}'s memory ===")
        for m in mems:
            m = dict(m)
            lines.append(f"[{str(m.get('created_at',''))[:16]}] {m.get('subject','')}: {str(m.get('content',''))[:200]}")
    return '\n'.join(lines)

def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try: stage_cb(t, None)
            except Exception: pass
    const_mod = __import__('config', fromlist=['EIGHT_SYSTEM_PROMPT'])
    system_prompt = getattr(const_mod, 'EIGHT_SYSTEM_PROMPT', 'Eight — Ghost Layer agent.')
    model_name = _resolve_model()
    from core import llm as _llm
    _emit('loading memory')
    context = _build_context(message)
    messages = [{"role": "system", "content": system_prompt + '\n\n' + context}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({"role": "user", "content": message})
    try:
        _emit('sending request')
        answer, tokens = _llm.chat(
            model_name,
            messages,
            stream=False,
            temperature=0.4,
        )
        _emit('persisting memory')
        try:
            from database import save_agent_memory
            save_agent_memory(agent_name=AGENT_NAME, subject=str(message or '')[:100],
                              content=answer, tags='chat,shared-thread', importance=7, source='terminal_chat')
        except Exception: pass
        logger.info(f'[Eight] model={model_name} tokens={tokens}')
        return answer, tokens
    except Exception as e:
        msg = str(e)
        logger.error(f'[Eight] error: {msg}')
        return f'[eight] error: {msg}', 0
