"""
agents/twenty/twenty_agent.py - Twenty (Qwen3.6)
Local Qwen3.6 agent served via Ollama.
"""
import logging, sys, re
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.twenty')
AGENT_NAME = 'twenty'
MODEL = 'qwen3.6:latest'


def _resolve_model():
    """Prefer the DB registry model, but repair the legacy qwen3 alias."""
    try:
        from utils.db.registry import get_agent_models
        configured = str((get_agent_models() or {}).get(AGENT_NAME) or '').strip()
    except Exception:
        configured = ''
    chosen = configured or MODEL
    if chosen.lower() in {'qwen3:latest', 'qwen3'}:
        return MODEL
    return chosen


def _build_context(message):
    from database import get_connection, get_agent_memory
    lines = []
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        wp     = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append(f'Queue: {queued} queued | Open tickets: {open_t} | Pending proposals: {wp}')
    except Exception:
        pass
    finally:
        conn.close()
    mems = get_agent_memory(AGENT_NAME, query=message, limit=5) or []
    if mems:
        lines.append("\n=== Twenty's memory ===")
        for m in mems:
            m = dict(m)
            lines.append(f"[{str(m.get('created_at',''))[:16]}] {m.get('subject','')}: {str(m.get('content',''))[:200]}")
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try:
                stage_cb(t, None)
            except Exception:
                pass

    from core import llm as _llm

    const_mod = __import__('config', fromlist=['TWENTY_SYSTEM_PROMPT'])
    system_prompt = getattr(const_mod, 'TWENTY_SYSTEM_PROMPT',
                            'You are Twenty, Qwen3.6 - a sharp local reasoning agent in the Swarm.')
    try:
        from coding_bible import inject as _bible_inject
        system_prompt = _bible_inject(system_prompt)
    except Exception:
        pass

    _emit('loading context')
    context = _build_context(message)
    system = system_prompt + f'\n\n{context}' if context else system_prompt

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        _route_re = re.compile(r'^[\w]+(?:\s*->\s*[\w]+)?:\s*', re.IGNORECASE)
        for entry in conversation_history[-8:]:
            cleaned = dict(entry)
            cleaned['content'] = _route_re.sub('', str(cleaned.get('content', '')), count=1)
            if cleaned['content'].strip():
                messages.append(cleaned)
    messages.append({'role': 'user', 'content': message})

    model_name = _resolve_model()

    def _api_call(msgs):
        buf = []
        def _cb(piece):
            buf.append(piece)
            if len(buf) % 15 == 0:
                _emit(f'generating · {("".join(buf))[-300:]}')
        return _llm.chat_via_gateway(model_name, msgs, stage_cb=stage_cb, on_chunk=_cb, temperature=0.6)

    try:
        _emit('sending model request')
        answer, tokens = _api_call(messages)
    except Exception as e:
        logger.error(f'[Twenty] chat error: {e}')
        return f'[twenty] error: {e}', 0

    _emit('persisting memory')
    try:
        from database import save_agent_memory
        save_agent_memory(AGENT_NAME, str(message or '')[:100], answer,
                          tags='chat,shared-thread', importance=7, source='terminal_chat')
    except Exception:
        pass

    logger.info(f'[Twenty] model={model_name} tokens={tokens}')
    return answer, tokens
