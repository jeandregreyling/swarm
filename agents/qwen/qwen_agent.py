"""
agents/qwen/qwen_agent.py — Qwen (local Ollama)
Deep reasoning analyst. Powered by qwen2.5:latest via Ollama.
"""
import logging, sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.qwen')
AGENT_NAME = 'qwen'
MODEL      = 'qwen2.5:latest'


def _build_context(message):
    from database import get_connection, get_agent_memory
    lines = []
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        lines.append(f'Queue: {queued} queued')
    except Exception:
        pass
    finally:
        conn.close()
    mems = get_agent_memory(AGENT_NAME, query=message, limit=5) or []
    if mems:
        lines.append(f"\n=== Qwen's memory ===")
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

    from config import QWEN_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system  = QWEN_SYSTEM_PROMPT + f'\n\n{context}' if context else QWEN_SYSTEM_PROMPT

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-8:])
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        buf = []
        def _cb(piece):
            buf.append(piece)
            if len(buf) % 15 == 0:
                _emit(f'generating · {("".join(buf))[-300:]}')
        return _llm.chat_via_gateway(MODEL, msgs, stage_cb=stage_cb, on_chunk=_cb, temperature=0.6)

    try:
        sys.path.insert(0, '/home/seven/swarm/agents')
        from agents.skills_loop import run_skill_loop
    except ImportError:
        from skills_loop import run_skill_loop

    try:
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME, call_fn=_api_call,
            messages=messages, emit_fn=_emit, max_passes=2, nudge_if_no_skills=True,
        )
    except Exception as e:
        return f'[qwen] error: {e}', 0

    _emit('persisting memory')
    try:
        from database import save_agent_memory
        save_agent_memory(AGENT_NAME, str(message or '')[:100], answer,
                          tags='chat,shared-thread', importance=7, source='terminal_chat')
    except Exception:
        pass

    logger.info(f'[Qwen] model={MODEL} tokens={tokens}')
    return answer, tokens
