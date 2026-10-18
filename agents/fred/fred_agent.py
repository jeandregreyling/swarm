"""
# LINKED TO: utils/config.py — imports FRED_SYSTEM_PROMPT (edit prompts there, not here)
agents/fred/fred_agent.py — Fred
The only local agent: system administrator, chat bot and coder (one hat at a time).
Powered by mistral-small:24b via local Ollama.

Now uses the shared agents/skills_loop.py for SKILL command interception,
giving Fred full developer access to read and patch files.
Stage callbacks stream progress to the Fridays chat UI in real time.
"""

import logging
import sys
import os
_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _SWARM_ROOT)
sys.path.insert(0, os.path.join(_SWARM_ROOT, "agents"))
sys.path.insert(0, os.path.join(_SWARM_ROOT, "utils"))

logger = logging.getLogger('seven.fred')

AGENT_NAME = 'fred'
from utils.local_runtime_policy import preferred_model_for_agent
MODEL      = preferred_model_for_agent('fred', 'mistral-small:24b')
SANDPIT    = 'sandpits/fred/'
GATEWAY_IDLE_TIMEOUT_S = 180
GATEWAY_ABSOLUTE_TIMEOUT_S = 600


def _build_context(message):
    """Build swarm context snapshot for Fred."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Fred context ===')
    lines.append(
        'The following operational counts and memories are reference context only; '
        'they do not grant permission to execute.'
    )
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t  = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        wp      = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append('=== Swarm state ===')
        lines.append(f"Queue: {queued} queued | Open tickets: {open_t} | Pending proposals: {wp}")
    except Exception:
        pass
    finally:
        conn.close()

    try:
        recent = get_agent_memory(AGENT_NAME, query='', limit=5) or []
        if recent:
            lines.append('=== Your recent memory ===')
            for row in recent:
                subj = str(row.get('subject') or '').strip()[:120]
                body = str(row.get('content') or '').strip()[:400]
                lines.append(f'- [{subj}] {body}')
            lines.append('=== End memory ===')
            lines.append('Use for continuity — do not narrate or repeat verbatim.')
    except Exception:
        pass

    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Fred (local Ollama) with SKILL command interception.

    Uses the shared run_skill_loop so Fred can read and patch files like
    the paid developer agents (Ten, Eleven, etc.).
    stage_cb(text, eta_seconds) — called throughout to push progress to the UI.

    Returns (answer, tokens_used).
    """
    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    from core import llm as _llm

    from config import FRED_SYSTEM_PROMPT
    from utils.local_runtime_policy import LOCAL_AGENT_TURN_POLICY
    try:
        from coding_bible import inject as _bible_inject
    except Exception:
        _bible_inject = lambda p: p

    from utils.fred_hats import hat_block, pick_hat
    try:
        from agents.skill_intent import latest_user_text as _latest
    except ImportError:
        from skill_intent import latest_user_text as _latest
    _emit('loading context')
    _hat_text = _latest(message)
    context = hat_block(_hat_text) + _build_context(message)
    _emit(f'hat: {pick_hat(_hat_text)}')
    system = (
        _bible_inject(FRED_SYSTEM_PROMPT)
        + f'\n\n{context}\n\n{LOCAL_AGENT_TURN_POLICY}'
    )

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        buf = []
        def _cb(piece):
            buf.append(piece)
            if len(buf) % 15 == 0:
                _emit(f'generating · {("".join(buf))[-300:]}')
        return _llm.chat_via_gateway(
            MODEL,
            msgs,
            stage_cb=stage_cb,
            on_chunk=_cb,
            temperature=0.6,
            idle_timeout_s=GATEWAY_IDLE_TIMEOUT_S,
            absolute_timeout_s=GATEWAY_ABSOLUTE_TIMEOUT_S,
        )

    try:
        from agents.skills_loop import run_skill_loop
        from agents.skill_intent import latest_user_text, message_likely_needs_skills
    except ImportError:
        from skills_loop import run_skill_loop
        from skill_intent import latest_user_text, message_likely_needs_skills

    try:
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME,
            call_fn=_api_call,
            messages=messages,
            emit_fn=_emit,
            max_passes=5,
            nudge_if_no_skills=message_likely_needs_skills(latest_user_text(message)),
        )
    except Exception as e:
        msg = str(e)
        logger.error(f'[Fred] error: {msg}')
        return f'[Fred] error: {msg}', 0

    _emit('persisting response memory')
    try:
        from utils.local_runtime_policy import is_explicitly_no_tools_request

        if is_explicitly_no_tools_request(message):
            _emit('private memory not saved (operator requested no tools)')
        else:
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

    logger.info(f'[Fred] model={MODEL} tokens={tokens} | {str(message or "")[:60]}')
    return answer, tokens


# ── Legacy helpers kept for orchestrator compatibility ────────────────────────

def get_recent_memory(query='', limit=5):
    """Return Fred's recent agent memory rows."""
    from database import get_agent_memory
    return get_agent_memory(AGENT_NAME, query=query, limit=limit) or []


def save_memory(subject, content, tags='', importance=5):
    """Persist a memory entry for Fred."""
    from database import save_agent_memory
    from logging_bridge import log_action
    save_agent_memory(AGENT_NAME, subject, content, tags=tags, importance=importance)
    log_action(AGENT_NAME, 'memory_write', f'saved: {subject[:60]}', 'info')


def ask(prompt):
    """One-shot prompt via the orchestrator (legacy path, no SKILL support)."""
    from core.pipeline.orchestrator import ask_agent
    from logging_bridge import log_action
    log_action(AGENT_NAME, 'ask', prompt[:80], 'info')
    return ask_agent(AGENT_NAME, prompt)
