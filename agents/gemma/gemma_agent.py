"""
agents/gemma/gemma_agent.py — Gemma (local Ollama)
Orchestrator agent. Powered by gemma3:latest via Ollama.
"""
import logging, sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.gemma')
AGENT_NAME = 'gemma'
MODEL      = 'gemma3:latest'


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
        lines.append(f"\n=== Gemma's memory ===")
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
        return '[gemma] ollama package not installed', 0

    from config import GEMMA_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system  = GEMMA_SYSTEM_PROMPT + f'\n\n{context}' if context else GEMMA_SYSTEM_PROMPT

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-8:])
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        chunks, token_count, tokens = [], 0, 0
        try:
            stream = _ollama.chat(
                model=MODEL, messages=msgs,
                options={'temperature': 0.7}, keep_alive=-1, stream=True,
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
            logger.warning(f'[Gemma] stream fallback: {exc}')
            resp = _ollama.chat(model=MODEL, messages=msgs, options={'temperature': 0.7}, keep_alive=-1)
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
            messages=messages, emit_fn=_emit, max_passes=5, nudge_if_no_skills=True,
        )
    except Exception as e:
        return f'[gemma] error: {e}', 0

    _emit('persisting memory')
    try:
        from database import save_agent_memory
        save_agent_memory(AGENT_NAME, str(message or '')[:100], answer,
                          tags='chat,shared-thread', importance=7, source='terminal_chat')
    except Exception:
        pass

    logger.info(f'[Gemma] model={MODEL} tokens={tokens}')
    return answer, tokens
