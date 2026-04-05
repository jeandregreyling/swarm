"""
# LINKED TO: utils/config.py — imports THIRTEEN_SYSTEM_PROMPT (edit prompts there, not here)
agents/thirteen/thirteen_agent.py — Thirteen (HuggingFace Inference API)
Developer Agent — HuggingFace specialist (testing). Powered by HuggingFace Inference API via OpenAI-compatible endpoint.
"""

import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/frontend')

logger = logging.getLogger('seven.thirteen')

AGENT_NAME  = 'thirteen'
HF_BASE_URL = 'https://router.huggingface.co/v1'
HF_MODEL    = 'meta-llama/Llama-3.3-70B-Instruct'


def _build_context(message):
    from database import get_connection, get_agent_memory
    lines = [
        '=== Governance rules (ALM) ===',
        'Mutating changes require approved work proposals (approved/executed).',
        'Use proposal-first guidance and include proposal IDs for execution paths.',
    ]
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        lines.append(f'=== Swarm state ===')
        lines.append(f'Queue: {queued} queued | Open tickets: {open_t}')
    finally:
        conn.close()
    relevant = get_agent_memory(AGENT_NAME, query=message, limit=5)
    if relevant:
        lines.append("\n=== Thirteen's relevant memory ===")
        for m in relevant:
            m = dict(m)
            lines.append(f"[{str(m.get('created_at',''))[:16]}] {m.get('subject','')}: {str(m.get('content',''))[:200]}")
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Thirteen (HuggingFace Inference API).
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
        return '[Thirteen] openai package not installed', 0

    from config import HF_API_TOKEN, THIRTEEN_SYSTEM_PROMPT
    system_prompt = THIRTEEN_SYSTEM_PROMPT
    hf_key = HF_API_TOKEN
    if not hf_key:
        logger.error('[Thirteen] HF_API_TOKEN not configured')
        return '[Thirteen] HF_API_TOKEN not set in .env.agents', 0

    _emit('loading ghost-layer memory')
    context = _build_context(message)
    system = system_prompt + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    try:
        _emit('sending model request to HuggingFace')
        client = OpenAI(api_key=hf_key, base_url=HF_BASE_URL)
        response = client.chat.completions.create(
            model=HF_MODEL,
            messages=messages,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0

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

        logger.info(f'[Thirteen] tokens={tokens} | {message[:60]}')
        return answer, tokens

    except Exception as e:
        msg = str(e)
        logger.error(f'[Thirteen] API error: {msg}')
        if '401' in msg or 'authentication' in msg.lower() or 'unauthorized' in msg.lower():
            return '[Thirteen] HF API key invalid or expired.', 0
        if '429' in msg or 'rate limit' in msg.lower():
            return f'[Thirteen] HuggingFace rate limit hit. {msg}', 0
        if '503' in msg or 'loading' in msg.lower():
            return f'[Thirteen] Model is loading on HuggingFace servers, try again in a moment.', 0
        return f'[Thirteen] API error: {msg}', 0
