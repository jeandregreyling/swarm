"""
# LINKED TO: utils/config.py — imports MISTRAL_SYSTEM_PROMPT (edit prompts there, not here)
agents/mistral/mistral_agent.py — Mistral
Local Ollama generalist analyst. Powered by mistral:latest.

Now uses the shared agents/skills_loop.py for SKILL command interception,
giving Mistral full developer access to read and patch files.
Stage callbacks stream progress to the Fridays chat UI in real time.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')

logger = logging.getLogger('seven.mistral')

AGENT_NAME = 'mistral'
MODEL      = 'mistral:latest'
SANDPIT    = 'sandpits/mistral/'


def _build_context(message):
    """Build swarm context snapshot for Mistral."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Mistral context ===')
    lines.append('You are a Developer Agent operating under Ghost One direction. Execute directly — no proposal queue for Ghost One-directed work.')
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
    Send a message to Mistral (local Ollama) with SKILL command interception.

    Uses the shared run_skill_loop so Mistral can read and patch files like
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

    try:
        import ollama as _ollama
    except ImportError:
        logger.error('[Mistral] ollama package not installed')
        return None, 0

    from config import MISTRAL_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system  = MISTRAL_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        chunks = []
        tokens = 0
        token_count = 0
        try:
            stream = _ollama.chat(
                model=MODEL,
                messages=msgs,
                options={'temperature': 0.6},
                keep_alive=300,
                stream=True,
            )
            for chunk in stream:
                part = (chunk.get('message') or {}).get('content') or ''
                if part:
                    chunks.append(part)
                    token_count += 1
                    # Push partial text to WIP box every 15 tokens so Ghost sees it typing
                    if token_count % 15 == 0:
                        partial = ''.join(chunks)[-300:]  # last 300 chars fits stage label
                        _emit(f'generating · {partial}')
                if chunk.get('done'):
                    tokens = int(chunk.get('eval_count') or 0)
        except Exception as exc:
            logger.warning(f'[Mistral] stream error, falling back to blocking call: {exc}')
            resp = _ollama.chat(
                model=MODEL,
                messages=msgs,
                options={'temperature': 0.6},
                keep_alive=300,
            )
            chunks = [resp['message']['content']]
            try:
                tokens = int(getattr(resp, 'eval_count', None) or resp.get('eval_count') or 0)
            except Exception:
                tokens = 0
        content = ''.join(chunks)
        return content, tokens

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
            nudge_if_no_skills=True,
        )
    except Exception as e:
        msg = str(e)
        logger.error(f'[Mistral] error: {msg}')
        return f'[Mistral] error: {msg}', 0

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

    logger.info(f'[Mistral] model={MODEL} tokens={tokens} | {str(message or "")[:60]}')
    return answer, tokens


# ── Legacy helpers kept for orchestrator compatibility ────────────────────────

def get_recent_memory(query='', limit=5):
    """Return Mistral's recent agent memory rows."""
    from database import get_agent_memory
    return get_agent_memory(AGENT_NAME, query=query, limit=limit) or []


def save_memory(subject, content, tags='', importance=5):
    """Persist a memory entry for Mistral."""
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
