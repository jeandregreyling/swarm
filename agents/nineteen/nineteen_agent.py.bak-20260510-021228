"""
# LINKED TO: utils/config.py — imports NINETEEN_SYSTEM_PROMPT (edit prompts there, not here)
agents/nineteen/nineteen_agent.py — Nineteen (o4-mini)
Fast reasoning agent. Powered by o4-mini via GitHub Models API.
Uses a GitHub PAT with models:read scope via https://models.inference.ai.azure.com

Uses the shared agents/skills_loop.py for SKILL command interception.
Stage callbacks stream progress to the Fridays chat UI in real time.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.nineteen')

AGENT_NAME = 'nineteen'
_DEFAULT_MODEL = 'o4-mini'


def _build_context(message):
    """Build swarm context snapshot for Nineteen."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Reasoning Agent context ===')
    lines.append('You are a Reasoning Agent operating under Ghost One direction. Execute directly — no proposal queue for Ghost One-directed work.')
    lines.append('Worker Agent requests still require proposal approval.')
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        wp_pending = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append('=== Swarm state ===')
        lines.append(f"Queue: {queued} queued | Open tickets: {open_t} | Pending proposals: {wp_pending}")
    except Exception:
        pass
    finally:
        conn.close()

    try:
        recent = get_agent_memory('nineteen', query='', limit=5) or []
        if recent:
            lines.append('=== Your recent memory (most important first) ===')
            for row in recent:
                subj = str(row.get('subject') or '').strip()[:120]
                body = str(row.get('content') or '').strip()[:400]
                lines.append(f'- [{subj}] {body}')
            lines.append('=== End memory ===')
            lines.append('Use this for continuity but do not narrate or repeat it verbatim.')
    except Exception:
        pass

    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None, conv_id=None):
    """
    Send a message to Nineteen (o4-mini via GitHub Models API).

    Uses the shared run_skill_loop for SKILL command interception.
    stage_cb(text, eta_seconds) — called throughout to push progress to the UI.
    conv_id: originating conversation ID — forwarded to alm_create_proposal so Duck can notify the thread.

    Returns (answer, tokens_used).
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
        logger.error('[Nineteen] openai package not installed')
        return None, 0

    from config import GITHUB_TOKEN, NINETEEN_SYSTEM_PROMPT, NINETEEN_MODEL
    if not GITHUB_TOKEN:
        logger.error('[Nineteen] GITHUB_TOKEN not configured — add to .env.agents')
        return None, 0

    _emit('loading context')
    context = _build_context(message)
    system = NINETEEN_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({'role': 'user', 'content': message})

    # ── API call wrapper for skills_loop ───────────────────────────────────────
    model = NINETEEN_MODEL or _DEFAULT_MODEL

    try:
        client = OpenAI(
            api_key=GITHUB_TOKEN,
            base_url='https://models.inference.ai.azure.com',
        )
    except Exception as e:
        return f'[Nineteen] Client init error: {e}', 0

    def _api_call(msgs):
        response = client.chat.completions.create(
            model=model,
            messages=msgs,
            max_completion_tokens=16384,
        )
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        return content, tokens

    # ── Run through shared skill loop ──────────────────────────────────────────
    try:
        sys.path.insert(0, '/home/seven/swarm/agents')
        from agents.skills_loop import run_skill_loop
    except ImportError:
        from skills_loop import run_skill_loop

    try:
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME,
            call_fn=_api_call,
            messages=messages,
            emit_fn=_emit,
            max_passes=5,
            max_skill_chars=2500,
            source_conv_id=conv_id,
        )
    except Exception as e:
        msg = str(e)
        logger.error(f'[Nineteen] API error: {msg}')
        if 'RateLimitReached' in msg or '429' in msg or 'rate limit' in msg.lower():
            return f'[Nineteen] GitHub Models rate limit reached. Resets in ~24h. Error: {msg}', 0
        if '401' in msg or 'Unauthorized' in msg or 'authentication' in msg.lower():
            return '[Nineteen] GitHub token rejected (401). Regenerate PAT with Models scope at github.com/settings/tokens.', 0
        return f'[Nineteen] API error: {msg}', 0

    _emit('persisting response memory')
    try:
        from database import save_agent_memory
        save_agent_memory(
            agent_name='nineteen',
            subject=str(message or '')[:100],
            content=answer,
            tags='chat,shared-thread',
            importance=7,
            source='terminal_chat',
        )
    except Exception:
        pass

    logger.info(f'[Nineteen] model={model} tokens={tokens} | {str(message or "")[:60]}')
    return answer, tokens
