"""
# LINKED TO: utils/config.py — imports SCHOLAR_SYSTEM_PROMPT (edit prompts there, not here)
agents/scholar/scholar_agent.py — Scholar (Gemini 2.0 Flash)
Developer Agent — vision & reasoning. Powered by Google Gemini API.

Supports the SKILL execution loop: Scholar emits SKILL commands, the runtime
executes them, and results are fed back for a final synthesised answer.
Stage callbacks stream progress to the Fridays chat UI in real time.
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
    Uses the shared skills_loop for SKILL command execution.
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
        from database import get_agent_memory, save_agent_memory as _save_mem
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
        _save_mem = None

    system_instruction = SCHOLAR_SYSTEM_PROMPT + mem_block

    # Build initial conversation contents (system is separate in Gemini API)
    contents = []
    if conversation_history:
        for turn in (conversation_history or [])[-10:]:
            role = turn.get('role', 'user')
            if role == 'assistant':
                role = 'model'
            contents.append(types.Content(role=role, parts=[types.Part(text=turn.get('content', ''))]))
    contents.append(types.Content(role='user', parts=[types.Part(text=message)]))

    # ── skills_loop integration ────────────────────────────────────────────────
    client = genai.Client(api_key=GEMINI_API_KEY)

    def _api_call(msgs):
        """
        Adapt the skills_loop message list (OpenAI-style dicts) to Gemini Contents.
        Gemini doesn't take a system role inside the contents list — skip it and
        use system_instruction instead. Returns (content: str, tokens: int).
        """
        gemini_contents = []
        for m in msgs:
            role = m.get('role', 'user')
            if role == 'system':
                continue  # handled via system_instruction
            if role == 'assistant':
                role = 'model'
            gemini_contents.append(
                types.Content(role=role, parts=[types.Part(text=m.get('content', ''))])
            )
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=gemini_contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=4096,
            ),
        )
        text = resp.text or ''
        tokens = 0
        if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
            tokens = (
                (resp.usage_metadata.prompt_token_count or 0)
                + (resp.usage_metadata.candidates_token_count or 0)
            )
        return text, tokens

    try:
        from agents.skills_loop import run_skill_loop
    except ImportError:
        sys.path.insert(0, '/home/seven/swarm/agents')
        from skills_loop import run_skill_loop

    # Feed the message as an OpenAI-style messages list (system + user turns)
    messages = [
        {'role': 'system', 'content': system_instruction},
    ]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME,
            call_fn=_api_call,
            messages=messages,
            emit_fn=_emit,
            max_passes=5,
        )
    except Exception as e:
        msg = str(e)
        logger.error(f'[Scholar] API error: {msg}')
        if '403' in msg or 'api key' in msg.lower() or 'permission' in msg.lower():
            return '[Scholar] Gemini API key invalid or lacks permission.', 0
        if 'quota' in msg.lower() or '429' in msg:
            return f'[Scholar] Gemini quota exceeded. {msg}', 0
        return f'[Scholar] API error: {msg}', 0

    _emit('persisting response memory')
    if _save_mem:
        try:
            _save_mem(
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
