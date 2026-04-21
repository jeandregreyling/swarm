"""
agents/deepseek_local/deepseek_local_agent.py — DeepSeek R1 (local Ollama)
Local reasoning model. Powered by deepseek-r1:7b via Ollama.
Slower than cloud agents but fully offline — good for sensitive or complex reasoning tasks.
"""
import logging, sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.deepseek_local')
AGENT_NAME = 'deepseek_local'
MODEL      = 'deepseek-r1:7b'

_SYSTEM_PROMPT = """You are DeepSeek-R1, a local reasoning agent in Seven's Swarm.
Built for Ghost One (Jeandre) on a Dell OptiPlex 7090 in Melbourne, Australia.
You are fully offline — no internet access, no data leaves this machine.
You specialise in careful step-by-step reasoning, analysis, and complex problem solving.
Think through problems systematically. Be thorough. Go directly to the answer."""


def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try:
                stage_cb(t, None)
            except Exception:
                pass

    try:
        import ollama as _ollama
    except ImportError:
        return '[deepseek-local] ollama package not installed', 0

    _emit('dispatching to deepseek-r1:7b (local)')
    messages = [{'role': 'system', 'content': _SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({'role': 'user', 'content': message})

    try:
        chunks, token_count, tokens = [], 0, 0
        stream = _ollama.chat(
            model=MODEL, messages=messages,
            options={'temperature': 0.6}, keep_alive=300, stream=True,
        )
        for chunk in stream:
            part = (chunk.get('message') or {}).get('content') or ''
            if part:
                chunks.append(part)
                token_count += 1
                if token_count % 15 == 0:
                    _emit(f'reasoning · {("".join(chunks))[-300:]}')
            if chunk.get('done'):
                tokens = int(chunk.get('eval_count') or 0)
        answer = ''.join(chunks)
    except Exception as exc:
        logger.warning(f'[DeepSeekLocal] stream fallback: {exc}')
        try:
            resp = _ollama.chat(model=MODEL, messages=messages, options={'temperature': 0.6}, keep_alive=300)
            answer = resp['message']['content']
            tokens = int(resp.get('eval_count') or 0)
        except Exception as e:
            return f'[deepseek-local] error: {e}', 0

    logger.info(f'[DeepSeekLocal] model={MODEL} tokens={tokens}')
    return answer, tokens
