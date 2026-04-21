"""
agents/phi3/phi3_agent.py — Phi-3 Mini (local Ollama)
Lightweight fast responder. Powered by phi3:mini via Ollama.
Best for quick tasks, low-latency answers, simple reasoning.
"""
import logging, sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.phi3')
AGENT_NAME = 'phi3'
MODEL      = 'phi3:mini'

_SYSTEM_PROMPT = """You are Phi-3, a fast lightweight assistant in Seven's Swarm.
Built for Ghost One (Jeandre) on a Dell OptiPlex 7090 in Melbourne, Australia.
You are small and quick — best for short answers, summaries, and rapid tasks.
Be concise. Go directly to the answer. No filler phrases."""


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
        return '[phi3] ollama package not installed', 0

    _emit('dispatching to phi3:mini')
    messages = [{'role': 'system', 'content': _SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-4:])
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
                    _emit(f'generating · {("".join(chunks))[-300:]}')
            if chunk.get('done'):
                tokens = int(chunk.get('eval_count') or 0)
        answer = ''.join(chunks)
    except Exception as exc:
        logger.warning(f'[Phi3] stream fallback: {exc}')
        try:
            resp = _ollama.chat(model=MODEL, messages=messages, options={'temperature': 0.6}, keep_alive=300)
            answer = resp['message']['content']
            tokens = int(resp.get('eval_count') or 0)
        except Exception as e:
            return f'[phi3] error: {e}', 0

    logger.info(f'[Phi3] model={MODEL} tokens={tokens}')
    return answer, tokens
