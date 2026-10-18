"""
# LINKED TO: utils/config.py — imports GEMINI_SYSTEM_PROMPT (edit prompts there, not here)
agents/gemini/gemini_agent.py — Gemini (Google Gemini API)
Developer Agent (Agent 18) — long-context analysis and multimodal reasoning.

Distinct from Scholar, the silent vision service that shares GEMINI_API_KEY.
Uses the shared skills_loop, so every skill remains subject to backend
permission, trust, and approval checks.
"""

import logging
import os
import sys
import time

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _SWARM_ROOT)
sys.path.insert(0, os.path.join(_SWARM_ROOT, 'agents'))
sys.path.insert(0, os.path.join(_SWARM_ROOT, 'utils'))

logger = logging.getLogger('seven.gemini')

AGENT_NAME = 'gemini'
_FALLBACK_MODELS = (
    'gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.6-flash', 'gemini-3.5-flash',
    'gemini-2.5-flash',
)
_RETRIES = 2


def _is_transient(exc):
    text = str(exc)
    return any(c in text for c in ('503', '500', '429', 'UNAVAILABLE', 'overloaded'))


def _memory_block():
    try:
        from database import get_agent_memory

        rows = [dict(r) for r in (get_agent_memory(AGENT_NAME, query='', limit=5) or [])]
    except Exception:
        return ''
    if not rows:
        return ''
    lines = [
        f"- [{str(r.get('subject') or '').strip()[:120]}] {str(r.get('content') or '').strip()[:400]}"
        for r in rows
    ]
    return '\n\n=== Your recent memory ===\n' + '\n'.join(lines) + '\n=== End memory ===\n'


def chat(message, conversation_history=None, stage_cb=None, conv_id=None):
    """Send a message to Gemini. Returns (answer, tokens_used)."""

    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return '[Gemini] google-genai package not installed. Run: pip install google-genai', 0

    from config import GEMINI_AGENT_MODEL, GEMINI_API_KEY, GEMINI_SYSTEM_PROMPT

    if not GEMINI_API_KEY:
        return '[Gemini] GEMINI_API_KEY not configured', 0

    _emit('loading context')
    system_instruction = GEMINI_SYSTEM_PROMPT + _memory_block()
    client = genai.Client(api_key=GEMINI_API_KEY)

    def _api_call(msgs):
        contents = []
        for m in msgs:
            role = m.get('role', 'user')
            if role == 'system':
                continue
            if role == 'assistant':
                role = 'model'
            contents.append(
                types.Content(role=role, parts=[types.Part(text=str(m.get('content', '')))])
            )
        cfg = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=4096,
        )
        models = [GEMINI_AGENT_MODEL] + [
            m for m in _FALLBACK_MODELS if m != GEMINI_AGENT_MODEL
        ]
        resp = None
        last_err = None
        for model in models:
            for attempt in range(_RETRIES):
                try:
                    resp = client.models.generate_content(
                        model=model, contents=contents, config=cfg
                    )
                    break
                except Exception as e:
                    last_err = e
                    if not _is_transient(e):
                        raise
                    _emit(f'{model} busy, trying next')
                    if '429' in str(e):
                        break
                    time.sleep(2 * (attempt + 1))
            if resp is not None:
                break
        if resp is None:
            raise last_err
        usage = getattr(resp, 'usage_metadata', None)
        tokens = 0
        if usage:
            tokens = (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)
        return resp.text or '', tokens

    messages = [{'role': 'system', 'content': system_instruction}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        from agents.skills_loop import run_skill_loop

        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME,
            call_fn=_api_call,
            messages=messages,
            emit_fn=_emit,
            max_passes=5,
            source_conv_id=conv_id,
        )
    except Exception as e:
        msg = str(e)
        logger.error(f'[Gemini] API error: {msg}')
        low = msg.lower()
        if '403' in msg or 'api key' in low or 'permission' in low:
            return '[Gemini] API key invalid or lacks permission.', 0
        if 'quota' in low or '429' in msg:
            return f'[Gemini] quota exceeded. {msg}', 0
        return f'[Gemini] API error: {msg}', 0

    _emit('persisting response memory')
    try:
        from utils.local_runtime_policy import is_explicitly_no_tools_request

        if not is_explicitly_no_tools_request(message):
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

    logger.info(f'[Gemini] model={GEMINI_AGENT_MODEL} tokens={tokens} | {str(message or "")[:60]}')
    return answer, tokens
