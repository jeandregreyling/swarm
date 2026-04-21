"""
agents/llama/llama_agent.py — LLaMA (local Ollama)
Fast internet-connected researcher. Powered by llama3.2:latest via Ollama.
"""
import logging, sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.llama')
AGENT_NAME = 'llama'
MODEL      = 'llama3.2:latest'


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
    mems = get_agent_memory(AGENT_NAME, query=message, limit=4) or []
    if mems:
        lines.append(f"\n=== LLaMA's memory ===")
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

    try:
        import ollama as _ollama
    except ImportError:
        return '[llama] ollama package not installed', 0

    from config import LLAMA_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system  = LLAMA_SYSTEM_PROMPT + f'\n\n{context}' if context else LLAMA_SYSTEM_PROMPT

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        chunks, token_count, tokens = [], 0, 0
        try:
            stream = _ollama.chat(
                model=MODEL, messages=msgs,
                options={'temperature': 0.7}, keep_alive=300, stream=True,
            )
            for chunk in stream:
                part = (chunk.get('message') or {}).get('content') or ''
                if part:
                    chunks.append(part)
                    token_count += 1
                    if token_count % 15 == 0:
                        _emit(f'generating · {("".join(chunks))[-300:]}')
                if chunk.get('done'):
                    tokens = int(chunk.get('eval_count') or 0)
        except Exception as exc:
            logger.warning(f'[LLaMA] stream fallback: {exc}')
            resp = _ollama.chat(model=MODEL, messages=msgs, options={'temperature': 0.7}, keep_alive=300)
            chunks = [resp['message']['content']]
            tokens = int(resp.get('eval_count') or 0)
        return ''.join(chunks), tokens

    try:
        sys.path.insert(0, '/home/seven/swarm/agents')
        from agents.skills_loop import run_skill_loop
    except ImportError:
        from skills_loop import run_skill_loop

    try:
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME, call_fn=_api_call,
            messages=messages, emit_fn=_emit, max_passes=3, nudge_if_no_skills=True,
        )
    except Exception as e:
        return f'[llama] error: {e}', 0

    _emit('persisting memory')
    try:
        from database import save_agent_memory
        save_agent_memory(AGENT_NAME, str(message or '')[:100], answer,
                          tags='chat,shared-thread', importance=6, source='terminal_chat')
    except Exception:
        pass

    logger.info(f'[LLaMA] model={MODEL} tokens={tokens}')
    return answer, tokens
