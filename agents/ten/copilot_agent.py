"""
agents/ten/copilot_agent.py — Ten (GPT)
Ghost Layer software engineering advisor. Powered by GPT via GitHub Models API.
Uses a GitHub PAT with models:read scope via https://models.inference.ai.azure.com
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')

logger = logging.getLogger('seven.ten')

AGENT_NAME = 'ten'
_DEFAULT_MODEL = 'gpt-4.1'


def _build_context(message):
    """Build swarm context snapshot for Ten."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Governance rules (ALM) ===')
    lines.append('Mutating changes require approved work proposals (approved/executed).')
    lines.append('Use proposal-first guidance and include proposal IDs for execution paths.')
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

    # Inject Ten's recent memories
    try:
        recent = get_agent_memory('ten', query='', limit=5) or []
        if recent:
            lines.append('=== Your recent memory ===')
            for row in recent:
                subj = str(row.get('subject') or '').strip()[:100]
                body = str(row.get('content') or '').strip()[:300]
                lines.append(f"- [{subj}] {body}")
    except Exception:
        pass

    return '\n'.join(lines)


def chat(message, conversation_history=None):
    """
    Send a message to Ten (GPT via GitHub Models API).
    Returns (answer, tokens_used).
    conversation_history: list of {role, content} dicts.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error('[Ten] openai package not installed')
        return None, 0

    from config import GITHUB_TOKEN, TEN_SYSTEM_PROMPT, TEN_MODEL
    if not GITHUB_TOKEN:
        logger.error('[Ten] GITHUB_TOKEN not configured — add to /etc/environment')
        return None, 0

    context = _build_context(message)
    system = TEN_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        client = OpenAI(
            api_key=GITHUB_TOKEN,
            base_url='https://models.inference.ai.azure.com',
        )
        response = client.chat.completions.create(
            model=TEN_MODEL or _DEFAULT_MODEL,
            messages=messages,
            max_tokens=4096,
        )
        answer = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        logger.info(f'[Ten] model={TEN_MODEL} tokens={tokens} | {message[:60]}')
        return answer, tokens
    except Exception as e:
        logger.error(f'[Ten] API error: {e}')
        return None, 0
