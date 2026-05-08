"""
# LINKED TO: utils/config.py — imports ELEVEN_SYSTEM_PROMPT (edit prompts there, not here)
agents/eleven/grok_agent.py — Eleven (Grok 3)
Developer Agent — lateral thinker. Powered by xAI Grok API.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')

logger = logging.getLogger('seven.eleven')

AGENT_NAME = 'eleven'


def _build_context(message):
    """Build swarm context snapshot for Eleven."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Developer Agent context ===')
    lines.append('You are a Developer Agent operating under Ghost One direction. Execute directly — no proposal queue for Ghost One-directed work.')
    lines.append('Worker Agent requests still require proposal approval.')
    lines.append('Draft ideas in sandpits first; cross-check options with Nine/Ten/Twelve before final recommendation.')
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        dec_count = conn.execute("SELECT COUNT(*) FROM decisions WHERE test_status='PASS'").fetchone()[0]
        wp_pending = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append(f"=== Swarm state ===")
        lines.append(f"Queue: {queued} queued | Open tickets: {open_t}")
        lines.append(f"Decisions logged (PASS): {dec_count} | Pending proposals: {wp_pending}")
        recent_dec = conn.execute(
            "SELECT decision_id, agent, decision, created_at FROM decisions ORDER BY decision_id DESC LIMIT 5"
        ).fetchall()
        if recent_dec:
            lines.append("Recent decisions:")
            for d in recent_dec:
                lines.append(f"  [{d['decision_id']}] {d['agent']}: {d['decision'][:80]}")
    finally:
        conn.close()
    relevant = get_agent_memory(AGENT_NAME, query=message, limit=5)
    if relevant:
        lines.append("\n=== PAST MEMORY RECORDS (database — NOT prior messages in this conversation) ===")
        for m in relevant:
            m = dict(m)
            lines.append(f"[RECORD {str(m.get('created_at',''))[:16]}] subject={m.get('subject','')!r} | {str(m.get('content',''))[:200]}")
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None, conv_id=None):
    """
    Send a message to Eleven (Grok 3). Returns (answer, tokens_used).
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
        from openai import OpenAI
    except ImportError:
        return None, 0

    from config import XAI_API_KEY, XAI_MODEL, ELEVEN_SYSTEM_PROMPT
    try:
        from coding_bible import inject as _bible_inject
    except Exception:
        _bible_inject = lambda p: p
    if not XAI_API_KEY:
        logger.error('[Eleven] XAI_API_KEY not configured')
        return None, 0

    _emit('loading context')
    context = _build_context(message)
    system = _bible_inject(ELEVEN_SYSTEM_PROMPT) + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        client = OpenAI(api_key=XAI_API_KEY, base_url='https://api.x.ai/v1')

        def _api_call(msgs):
            resp = client.chat.completions.create(
                model=XAI_MODEL,
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
            max_passes=10,
            nudge_if_no_skills=False,  # Grok handles SKILL commands fine when the task needs them; nudge causes confusion on general questions
            source_conv_id=conv_id,
        )

        _emit('persisting response memory')
        try:
            from database import save_agent_memory
            # Strip routing/relay context prefixes to get the actual user question
            _user_q = str(message or '')
            for _marker in ('=== End memory ===', '=== End knowledge broadcast ===', '=== EXECUTION CONFIRMATION ==='):
                if _marker in _user_q:
                    _user_q = _user_q[_user_q.rindex(_marker) + len(_marker):]
            _user_q = _user_q.strip().lstrip('\n')[:100]
            save_agent_memory(
                agent_name=AGENT_NAME,
                subject=_user_q or 'eleven terminal chat',
                content=answer,
                tags='chat,shared-thread',
                importance=7,
                source='terminal_chat',
            )
        except Exception:
            pass

        logger.info(f'[Eleven] tokens={tokens} | {message[:60]}')
        return answer, tokens
    except Exception as e:
        msg = str(e)
        logger.error(f'[Eleven] API error: {msg}')
        if '401' in msg or 'authentication' in msg.lower():
            return '[Eleven] xAI API key invalid or expired.', 0
        if '429' in msg or 'rate limit' in msg.lower():
            return f'[Eleven] xAI rate limit hit. {msg}', 0
        return f'[Eleven] API error: {msg}', 0
