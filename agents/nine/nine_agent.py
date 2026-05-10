"""
# LINKED TO: utils/config.py — imports NINE_SYSTEM_PROMPT (edit prompts there, not here)
agents/nine/nine_agent.py — Nine (Groq · llama-3.3-70b-versatile)
Developer Agent — system architect. Powered by Groq API.
"""

import logging
import sys
import os
_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_SWARM_ROOT, "utils"))

logger = logging.getLogger('seven.nine')

AGENT_NAME = 'nine'


def _build_context(message):
    """Build swarm context snapshot for Nine."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Developer Agent context ===')
    lines.append('You are a Developer Agent operating under Ghost One direction. Execute directly — no proposal queue for Ghost One-directed work.')
    lines.append('Worker Agent requests (Gemma, LLaMA, Mistral, Eight, Duck, Sniffles, Librarian) still require proposal approval.')
    lines.append('Draft architectural options in sandpits first; cross-check with Ten, Eleven, and Twelve before final recommendation.')
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        dec_count = conn.execute("SELECT COUNT(*) FROM decisions WHERE test_status='PASS'").fetchone()[0]
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
        lines.append('\n=== Nine\'s relevant memory ===')
        for m in relevant:
            m = dict(m)
            lines.append(f'[{str(m.get("created_at", ""))[:16]}] {m.get("subject", "")}: {str(m.get("content", ""))[:200]}')
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None, conv_id=None):
    """
    Send a message to Nine (llama-3.3-70b-versatile via Groq).
    Returns (answer, tokens_used).
    conversation_history: list of {role, content} dicts for multi-turn context.
    stage_cb(text, eta): called throughout for live progress in Fridays UI.
    conv_id: originating conversation ID — forwarded to alm_create_proposal so Duck can notify the thread.
    """
    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    try:
        from groq import Groq
    except ImportError:
        return None, 0

    from config import GROQ_API_KEY, NINE_MODEL, NINE_SYSTEM_PROMPT
    if not GROQ_API_KEY:
        logger.error('[Nine] GROQ_API_KEY not configured')
        return None, 0

    _emit('loading context')
    context = _build_context(message)
    system = NINE_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        client = Groq(api_key=GROQ_API_KEY)

        def _api_call(msgs):
            resp = client.chat.completions.create(
                model=NINE_MODEL,
                messages=msgs,
                max_tokens=4096,
            )
            return resp.choices[0].message.content, (resp.usage.total_tokens if resp.usage else 0)

        from agents.skills_loop import run_skill_loop
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME,
            call_fn=_api_call,
            messages=messages,
            emit_fn=_emit,
            source_conv_id=conv_id,
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

        logger.info(f'[Nine] tokens={tokens} | {message[:60]}')
        return answer, tokens
    except Exception as e:
        msg = str(e)
        logger.error(f'[Nine] API error: {msg}')
        if '401' in msg or 'authentication' in msg.lower():
            return '[Nine] Groq API key invalid or expired.', 0
        if '429' in msg or 'rate limit' in msg.lower():
            return f'[Nine] Groq rate limit hit. {msg}', 0
        return f'[Nine] API error: {msg}', 0
