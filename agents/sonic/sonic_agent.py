"""
agents/sonic/sonic_agent.py — Sonic (Claude 3.5 Sonnet)
Ghost Layer velocity coder. Fast, precise, code-focused.
Uses Anthropic API with the claude-3-5-sonnet model.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.sonic')

AGENT_NAME = 'sonic'
_DEFAULT_MODEL = 'claude-3-5-sonnet-20241022'


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Sonic (Claude 3.5 Sonnet). Returns (answer, tokens_used).
    Supports stage_cb(text, eta) for live progress in the Fridays UI.
    """
    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    try:
        import anthropic
    except ImportError:
        return '[Sonic] anthropic package not installed', 0

    from claude_api import _load_api_key
    from config import SONIC_SYSTEM_PROMPT

    api_key = _load_api_key()
    if not api_key:
        return '[Sonic] ANTHROPIC_API_KEY not configured', 0

    _emit('loading ghost-layer memory')
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
                '\n\n=== Your recent memory (most important first) ===\n'
                + '\n'.join(lines)
                + '\n=== End memory ===\n'
                + 'Use for continuity; do not narrate it.'
            )
    except Exception:
        mem_block = ''
        save_agent_memory = None

    system = SONIC_SYSTEM_PROMPT + mem_block

    messages = []
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        _emit('sending model request')
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_DEFAULT_MODEL,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

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

        logger.info(f'[Sonic] tokens={tokens} | {str(message or "")[:60]}')
        return answer, tokens
    except Exception as e:
        msg = str(e)
        logger.error(f'[Sonic] API error: {msg}')
        if 'credit balance' in msg.lower() or 'billing' in msg.lower():
            return '[Sonic] Anthropic credit balance too low. Add credits at console.anthropic.com/settings/billing.', 0
        if '401' in msg or 'authentication' in msg.lower():
            return '[Sonic] Anthropic API key invalid or expired.', 0
        return f'[Sonic] API error: {msg}', 0
