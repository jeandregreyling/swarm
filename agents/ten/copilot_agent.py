"""
# LINKED TO: utils/config.py — imports TEN_SYSTEM_PROMPT (edit prompts there, not here)
agents/ten/copilot_agent.py — Ten (GPT)
Developer Agent — software engineer. Powered by GPT via GitHub Models API.
Uses a GitHub PAT with models:read scope via https://models.inference.ai.azure.com

Uses the shared agents/skills_loop.py for SKILL command interception.
Stage callbacks stream progress to the Fridays chat UI in real time.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.ten')

AGENT_NAME = 'ten'
_DEFAULT_MODEL = 'gpt-4.1'


def _build_context(message):
    """Build swarm context snapshot for Ten."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Developer Agent context ===')
    lines.append('You are a Developer Agent operating under Ghost One direction. Execute directly — no proposal queue for Ghost One-directed work.')
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
        recent = get_agent_memory('ten', query='', limit=5) or []
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


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Ten (GPT via GitHub Models API).

    Uses the shared run_skill_loop for SKILL command interception.
    stage_cb(text, eta_seconds) — called throughout to push progress to the UI.

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
        logger.error('[Ten] openai package not installed')
        return None, 0

    from config import GITHUB_TOKEN, TEN_SYSTEM_PROMPT, TEN_MODEL
    if not GITHUB_TOKEN:
        logger.error('[Ten] GITHUB_TOKEN not configured — add to .env.agents')
        return None, 0

    _emit('loading context')
    context = _build_context(message)
    system = TEN_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        # gpt-4.1 has an 8000-token limit — keep history lean
        messages.extend(conversation_history[-4:])
    messages.append({'role': 'user', 'content': message})

    # ── API call wrapper for skills_loop ───────────────────────────────────────
    model = TEN_MODEL or _DEFAULT_MODEL

    try:
        client = OpenAI(
            api_key=GITHUB_TOKEN,
            base_url='https://models.inference.ai.azure.com',
        )
    except Exception as e:
        return f'[Ten] Client init error: {e}', 0

    def _api_call(msgs):
        response = client.chat.completions.create(
            model=model,
            messages=msgs,
            max_tokens=4096,
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
            max_skill_chars=2500,  # gpt-4.1 hard limit: 8000 tokens total
        )
    except Exception as e:
        msg = str(e)
        logger.error(f'[Ten] API error: {msg}')
        if 'RateLimitReached' in msg or '429' in msg or 'rate limit' in msg.lower():
            return f'[Ten] GitHub Models rate limit reached (50 req/day free tier). Resets in ~24h. Error: {msg}', 0
        if '401' in msg or 'Unauthorized' in msg or 'authentication' in msg.lower():
            return '[Ten] GitHub token rejected (401). Regenerate PAT with Models scope at github.com/settings/tokens.', 0
        return f'[Ten] API error: {msg}', 0

    _emit('persisting response memory')
    try:
        from database import save_agent_memory
        save_agent_memory(
            agent_name='ten',
            subject=str(message or '')[:100],
            content=answer,
            tags='chat,shared-thread',
            importance=7,
            source='terminal_chat',
        )
    except Exception:
        pass

    logger.info(f'[Ten] model={model} tokens={tokens} | {str(message or "")[:60]}')
    return answer, tokens
