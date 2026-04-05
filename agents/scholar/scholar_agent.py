"""
# LINKED TO: utils/config.py — imports SCHOLAR_SYSTEM_PROMPT (edit prompts there, not here)
agents/scholar/scholar_agent.py — Scholar (Gemini 2.0 Flash)
Developer Agent — vision & reasoning. Powered by Google Gemini API.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.scholar')

AGENT_NAME = 'scholar'


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Scholar (Gemini 2.0 Flash). Returns (answer, tokens_used).
    Supports stage_cb(text, eta) for live progress in the Fridays UI.
    """
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
        return '[Scholar] google-genai package not installed. Run: pip install google-genai', 0

    from config import GEMINI_API_KEY, GEMINI_MODEL, SCHOLAR_SYSTEM_PROMPT

    if not GEMINI_API_KEY:
        return '[Scholar] GEMINI_API_KEY not configured', 0

    _emit('loading context')
    try:
        from database import get_agent_memory, save_agent_memory
        recent = get_agent_memory(AGENT_NAME, query='', limit=5) or []
        mem_block = ''
        if recent:
            lines = []
            for row in recent:
                subj = str(row.get('subject') or '').strip()[:120]
                body = str(row.get('content') or '').strip()[:400]
                lines.append(f'- [{subj}] {body}')
            mem_block = (
                '\n\n=== Your recent memory ===\n'
                + '\n'.join(lines)
                + '\n=== End memory ===\n'
            )
    except Exception:
        mem_block = ''
        save_agent_memory = None

    system_instruction = SCHOLAR_SYSTEM_PROMPT + mem_block

    # Build conversation contents
    contents = []
    if conversation_history:
        for turn in conversation_history[-10:]:
            role = turn.get('role', 'user')
            # Gemini uses 'model' instead of 'assistant'
            if role == 'assistant':
                role = 'model'
            contents.append(types.Content(role=role, parts=[types.Part(text=turn.get('content', ''))]))
    contents.append(types.Content(role='user', parts=[types.Part(text=message)]))

    try:
        _emit('sending model request')
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=4096,
            ),
        )
        answer = response.text
        # Gemini usage metadata
        tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            tokens = (
                (response.usage_metadata.prompt_token_count or 0)
                + (response.usage_metadata.candidates_token_count or 0)
            )

        _emit('persisting response memory')
        if save_agent_memory:
            try:
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

        logger.info(f'[Scholar] model={GEMINI_MODEL} tokens={tokens} | {str(message or "")[:60]}')
        return answer, tokens
    except Exception as e:
        msg = str(e)
        logger.error(f'[Scholar] API error: {msg}')
        if '403' in msg or 'api key' in msg.lower() or 'permission' in msg.lower():
            return '[Scholar] Gemini API key invalid or lacks permission.', 0
        if 'quota' in msg.lower() or '429' in msg:
            return f'[Scholar] Gemini quota exceeded. {msg}', 0
        return f'[Scholar] API error: {msg}', 0
