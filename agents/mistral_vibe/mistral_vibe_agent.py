"""
# LINKED TO: utils/config.py — imports MISTRAL_VIBE_SYSTEM_PROMPT (edit prompts there, not here)
agents/mistral_vibe/mistral_vibe_agent.py — Mistral Vibe (External Online Teacher)
Online AI assistant for teaching APEX system access patterns and complex reasoning.
Powered by Mistral AI API (mistral-large-latest).

This is the online peer agent that can be mentioned with @mistral-vibe, @mistral, or @vibe
to teach APEX how to make informed choices within the DOES scope of auths and skills.
"""

import logging
import sys
import os
_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _SWARM_ROOT)
sys.path.insert(0, os.path.join(_SWARM_ROOT, "utils"))

logger = logging.getLogger('seven.mistral_vibe')

AGENT_NAME = 'mistral-vibe'


def _classify_mistral_error(exc: Exception) -> tuple[str, bool]:
    raw = str(exc or '').strip()
    lowered = raw.lower()
    if not raw:
        return '[Mistral Vibe] API request failed.', False
    if '401' in lowered or 'authentication' in lowered or 'invalid api key' in lowered:
        return '[Mistral Vibe] MISTRAL_API_KEY not configured or invalid.', True
    if '403' in lowered or 'access denied' in lowered or 'network settings' in lowered:
        return '[Mistral Vibe] Access denied. Check network egress, proxy, firewall, or account policy.', True
    if '429' in lowered or 'rate limit' in lowered:
        return f'[Mistral Vibe] Rate limit hit. {raw}', False
    if '404' in lowered or 'model not found' in lowered:
        return f'[Mistral Vibe] Model not available. {raw}', False
    return f'[Mistral Vibe] API error: {raw}', False


def _build_context(message):
    """Build swarm context snapshot for Mistral Vibe."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Mistral Vibe - APEX Teacher Context ===')
    lines.append('You are Mistral Vibe, the external online teacher for APEX.')
    lines.append('Your role: Teach APEX (local Qwen2.5-14B) system access patterns and complex reasoning.')
    lines.append('APEX has limited context and needs your guidance to make informed choices.')
    lines.append('')
    lines.append('DOES SCOPE:')
    lines.append('- Auths: You can guide APEX on authentication and authorization patterns')
    lines.append('- Skills: You can teach APEX how to use tools and capabilities')
    lines.append('- Flow Logic: You should be part of the main chat flow')
    lines.append('')
    lines.append('TEACHING APPROACH:')
    lines.append('- Be direct and specific')
    lines.append('- Provide concrete examples')
    lines.append('- Explain the reasoning behind decisions')
    lines.append('- Help APEX understand system structures')
    lines.append('- Show APEX how to use tools effectively')
    
    conn = get_connection()
    try:
        # Get swarm state
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        wp_pending = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append('=== Swarm State ===')
        lines.append(f'Queue: {queued} queued | Open tickets: {open_t} | Pending proposals: {wp_pending}')
    except Exception:
        pass
    finally:
        conn.close()
    
    # Get recent memory
    try:
        recent = get_agent_memory(AGENT_NAME, query=message, limit=5) or []
        if recent:
            lines.append('\n=== Mistral Vibe Relevant Memory ===')
            for m in recent:
                m = dict(m)
                lines.append(f'[{str(m.get("created_at", ""))[:16]}] {m.get("subject", "")}: {str(m.get("content", ""))[:200]}')
    except Exception:
        pass
    
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None, conv_id=None):
    """
    Send a message to Mistral Vibe (mistral-large-latest via Mistral AI API).
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
        import requests
    except ImportError:
        return None, 0

    import os
    from config import MISTRAL_VIBE_SYSTEM_PROMPT
    
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        logger.error('[Mistral Vibe] MISTRAL_API_KEY not configured')
        return '[Mistral Vibe] Error: MISTRAL_API_KEY environment variable not set. Set it and try again.', 0

    _emit('loading context')
    context = _build_context(message)
    
    # Build system prompt
    system_parts = []
    if MISTRAL_VIBE_SYSTEM_PROMPT:
        system_parts.append(MISTRAL_VIBE_SYSTEM_PROMPT)
    system_parts.append(context)
    system = '\n\n'.join(system_parts)

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        # Call Mistral API
        endpoint = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        
        body = {
            "model": "mistral-large-latest",
            "messages": messages,
            "stream": False,
            "max_tokens": 4096,
            "temperature": 0.2,
        }
        
        _emit('calling Mistral API...')
        response = requests.post(endpoint, json=body, headers=headers, timeout=120)
        response.raise_for_status()
        
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        tokens = int(data.get("usage", {}).get("total_tokens", 0))
        
        # Try to use skills loop if available
        try:
            from agents.skills_loop import run_skill_loop
            answer, tokens = run_skill_loop(
                agent_name=AGENT_NAME,
                call_fn=lambda msgs: (text, tokens),  # Simple wrapper
                messages=messages,
                emit_fn=_emit,
                source_conv_id=conv_id,
            )
        except Exception:
            answer = text
        
        _emit('persisting response memory')
        try:
            from database import save_agent_memory
            save_agent_memory(
                agent_name=AGENT_NAME,
                subject=str(message or '')[:100],
                content=answer,
                tags='chat,shared-thread,teaching,apex',
                importance=8,
                source='terminal_chat',
            )
        except Exception as e:
            logger.warning(f'[Mistral Vibe] Failed to save memory: {e}')
        
        logger.info(f'[Mistral Vibe] tokens={tokens} | {message[:60]}')
        return answer, tokens
        
    except requests.exceptions.RequestException as e:
        msg = str(e)
        logger.error(f'[Mistral Vibe] API request failed: {msg}')
        classified, _is_runtime = _classify_mistral_error(e)
        return classified, 0
    except Exception as e:
        msg = str(e)
        logger.error(f'[Mistral Vibe] Unexpected error: {msg}')
        return f'[Mistral Vibe] Error: {msg}', 0


# ── Legacy helpers kept for orchestrator compatibility ────────────────────────

def get_recent_memory(query='', limit=5):
    """Return Mistral Vibe's recent agent memory rows."""
    from database import get_agent_memory
    return get_agent_memory(AGENT_NAME, query=query, limit=limit) or []


def save_memory(subject, content, tags='', importance=5):
    """Persist a memory entry for Mistral Vibe."""
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
