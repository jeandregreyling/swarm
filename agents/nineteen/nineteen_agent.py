"""
# LINKED TO: utils/config.py — imports NINETEEN_SYSTEM_PROMPT (edit prompts there, not here)
agents/nineteen/nineteen_agent.py — Nineteen (local Ollama)
Fast reasoning agent powered by the installed local Qwen model.

Uses the shared agents/skills_loop.py for SKILL command interception.
Stage callbacks stream progress to the Fridays chat UI in real time.
"""

import logging
import sys
import os
_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _SWARM_ROOT)
sys.path.insert(0, os.path.join(_SWARM_ROOT, "agents"))
sys.path.insert(0, os.path.join(_SWARM_ROOT, "utils"))

logger = logging.getLogger('seven.nineteen')

AGENT_NAME = 'nineteen'
from utils.local_runtime_policy import preferred_model_for_agent
LOCAL_MODEL = preferred_model_for_agent(AGENT_NAME, 'qwen2.5:14b-instruct')


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
    Send a message to Nineteen through the local Ollama gateway.

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

    from config import NINETEEN_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system = NINETEEN_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        from core import llm
        return llm.chat_via_gateway(
            LOCAL_MODEL,
            msgs,
            stage_cb=stage_cb,
            temperature=0.4,
        )

    # ── Run through shared skill loop ──────────────────────────────────────────
    try:
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
        logger.error(f'[Nineteen] local inference error: {msg}')
        return f'[Nineteen] local inference error: {msg}', 0

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

    logger.info(f'[Nineteen] model={LOCAL_MODEL} tokens={tokens} | {str(message or "")[:60]}')
    return answer, tokens
