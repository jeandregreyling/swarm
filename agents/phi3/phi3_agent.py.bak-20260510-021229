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

    from core import llm as _llm

    _emit('dispatching to phi3:mini')
    messages = [{'role': 'system', 'content': _SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-4:])
    messages.append({'role': 'user', 'content': message})

    try:
        buf = []
        def _cb(piece):
            buf.append(piece)
            if len(buf) % 15 == 0:
                _emit(f'generating · {("".join(buf))[-300:]}')
        answer, tokens = _llm.chat_via_gateway(MODEL, messages, stage_cb=stage_cb, on_chunk=_cb, temperature=0.6)
    except Exception as exc:
        logger.warning(f'[Phi3] stream error: {exc}')
        return f'[phi3] error: {exc}', 0

    logger.info(f'[Phi3] model={MODEL} tokens={tokens}')
    return answer, tokens
