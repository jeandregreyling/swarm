"""
# LINKED TO: utils/config.py — imports THIRTEEN_SYSTEM_PROMPT (edit prompts there, not here)
agents/thirteen/thirteen_agent.py — Thirteen (local Ollama)
Developer Agent powered by the installed local Llama model.
"""

import logging
import sys
import os
_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_SWARM_ROOT, "frontend"))
sys.path.insert(0, os.path.join(_SWARM_ROOT, "utils"))

logger = logging.getLogger('seven.thirteen')

AGENT_NAME = 'thirteen'
LOCAL_MODEL = 'llama3.2:latest'


def _build_context(message):
    """Build swarm context snapshot for Thirteen."""
    from database import get_connection, get_agent_memory
    lines = [
        '=== Developer Agent context (TESTING) ===',
        'You are a Developer Agent operating under Ghost One direction. Execute directly — no proposal queue for Ghost One-directed work.',
        'You are in TESTING MODE: flag all outputs to Ghost One and prefer conservative actions until promoted.',
        'Worker Agent requests still require proposal approval.',
    ]
    conn = get_connection()
    try:
        queued  = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t  = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        dec_count  = conn.execute("SELECT COUNT(*) FROM decisions WHERE test_status='PASS'").fetchone()[0]
        wp_pending = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append('=== Swarm state ===')
        lines.append(f'Queue: {queued} queued | Open tickets: {open_t}')
        lines.append(f'Decisions logged (PASS): {dec_count} | Pending proposals: {wp_pending}')
        recent_dec = conn.execute(
            'SELECT decision_id, agent, decision, created_at FROM decisions ORDER BY decision_id DESC LIMIT 5'
        ).fetchall()
        if recent_dec:
            lines.append('Recent decisions:')
            for d in recent_dec:
                lines.append(f'  [{d["decision_id"]}] {d["agent"]}: {d["decision"][:80]}')
    finally:
        conn.close()
    relevant = get_agent_memory(AGENT_NAME, query=message, limit=5)
    if relevant:
        lines.append("\n=== Thirteen's relevant memory ===")
        for m in relevant:
            m = dict(m)
            lines.append(f"[{str(m.get('created_at',''))[:16]}] {m.get('subject','')}: {str(m.get('content',''))[:200]}")
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Thirteen through the local Ollama gateway.
    Returns (answer, tokens_used).
    """
    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    from config import THIRTEEN_SYSTEM_PROMPT
    system_prompt = THIRTEEN_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system = system_prompt + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        def _api_call(msgs):
            from core import llm
            return llm.chat_via_gateway(
                LOCAL_MODEL,
                msgs,
                stage_cb=stage_cb,
                temperature=0.5,
            )

        from agents.skills_loop import run_skill_loop
        from agents.skill_intent import message_likely_needs_skills
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME,
            call_fn=_api_call,
            messages=messages,
            emit_fn=_emit,
            nudge_if_no_skills=message_likely_needs_skills(message),
        )

        _emit('persisting response memory')
        try:
            from database import save_agent_memory
            save_agent_memory(
                agent_name=AGENT_NAME,
                subject=str(message or '')[:100],
                content=answer,
                tags='chat,shared-thread',
                importance=7,
                source='terminal_chat',
            )
        except Exception:
            pass

        logger.info(f'[Thirteen] model={LOCAL_MODEL} tokens={tokens} | {message[:60]}')
        return answer, tokens

    except Exception as e:
        logger.error(f'[Thirteen] local inference error: {e}')
        return f'[Thirteen] local inference error: {e}', 0
