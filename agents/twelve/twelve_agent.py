"""
agents/twelve/twelve_agent.py — Twelve (Claude Haiku)
Ghost Layer temporal awareness agent. Powered by Claude Haiku via Anthropic API.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')

logger = logging.getLogger('seven.twelve')

AGENT_NAME = 'twelve'


def _build_context(message):
    """Build temporal context snapshot for Twelve."""
    from database import get_connection, get_agent_memory
    lines = ['=== Time Wizard context ===']
    lines.append('=== Governance rules (ALM) ===')
    lines.append('Mutating operations must map to approved proposal IDs while ALM is active.')
    lines.append('Preserve proposal and decision traceability when recommending actions.')
    lines.append('Use sandpits for pre-change reasoning and bounce options with Nine/Ten/Eleven before execution.')
    conn = get_connection()
    try:
        # Recent decisions
        decisions = conn.execute(
            "SELECT decision_id, agent, decision, test_status, commit_hash, created_at "
            "FROM decisions ORDER BY decision_id DESC LIMIT 10"
        ).fetchall()
        if decisions:
            lines.append('Recent decisions:')
            for d in decisions:
                lines.append(
                    f"  [{d['decision_id']}] {d['agent']} | {d['test_status']} | "
                    f"{d['decision'][:80]} | {str(d['created_at'])[:16]}"
                )
        # Time machine snapshots
        tm_count = conn.execute('SELECT COUNT(*) FROM time_machine').fetchone()[0]
        lines.append(f'\nTime machine: {tm_count} file snapshots stored')
        recent_tm = conn.execute(
            "SELECT agent, file_path, outcome, created_at FROM time_machine "
            "ORDER BY checkpoint_id DESC LIMIT 5"
        ).fetchall()
        for t in recent_tm:
            lines.append(f"  {t['agent']}: {t['file_path']} ({t['outcome']}) {str(t['created_at'])[:16]}")
        # Work proposals
        proposals = conn.execute(
            "SELECT proposal_id, agent, title, status, created_at FROM work_proposals "
            "ORDER BY id DESC LIMIT 5"
        ).fetchall()
        if proposals:
            lines.append('\nWork proposals (recent):')
            for p in proposals:
                lines.append(f"  [{p['proposal_id']}] {p['agent']}: {p['title'][:60]} | {p['status']}")
        # Daily checkpoints
        checkpoints = conn.execute(
            "SELECT timestamp, description, decisions_count FROM daily_checkpoint "
            "ORDER BY checkpoint_id DESC LIMIT 5"
        ).fetchall()
        if checkpoints:
            lines.append('\nDaily checkpoints:')
            for c in checkpoints:
                lines.append(f"  {str(c['timestamp'])[:16]}: {c['decisions_count']} decisions | {str(c['description'] or '')[:60]}")
    finally:
        conn.close()
    relevant = get_agent_memory(AGENT_NAME, query=message, limit=5)
    if relevant:
        lines.append('\n=== Twelve relevant memory ===')
        for m in relevant:
            m = dict(m)
            lines.append(f"[{str(m.get('created_at',''))[:16]}] {m.get('subject','')}: {str(m.get('content',''))[:200]}")
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Twelve (Claude Haiku 4.5). Returns (answer, tokens_used).
    conversation_history: list of {role, content} dicts for multi-turn context.
    stage_cb(text, eta): called throughout for live progress in Fridays UI.
    """
    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    try:
        import anthropic
    except ImportError:
        return None, 0

    from claude_api import _load_api_key
    from config import HAIKU_MODEL, TWELVE_SYSTEM_PROMPT

    api_key = _load_api_key()
    if not api_key:
        logger.error('[Twelve] ANTHROPIC_API_KEY not configured')
        return '[Twelve] ANTHROPIC_API_KEY not configured', 0

    _emit('loading ghost-layer memory')
    context = _build_context(message)
    system = TWELVE_SYSTEM_PROMPT + f'\n\n{context}'

    messages = []
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        _emit('sending model request')
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

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

        logger.info(f'[Twelve] tokens={tokens} | {message[:60]}')
        return answer, tokens
    except Exception as e:
        msg = str(e)
        logger.error(f'[Twelve] API error: {msg}')
        if 'credit balance' in msg.lower() or 'billing' in msg.lower():
            return '[Twelve] Anthropic credit balance too low. Add credits at console.anthropic.com/settings/billing.', 0
        if '401' in msg or 'authentication' in msg.lower():
            return '[Twelve] Anthropic API key invalid or expired.', 0
        return f'[Twelve] API error: {msg}', 0
