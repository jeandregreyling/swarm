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

    from core import llm as _llm

    _emit('dispatching to deepseek-r1:7b (local)')
    messages = [{'role': 'system', 'content': _SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({'role': 'user', 'content': message})

    try:
        buf = []
        def _cb(piece):
            buf.append(piece)
            if len(buf) % 15 == 0:
                _emit(f'reasoning · {("".join(buf))[-300:]}')
        answer, tokens = _llm.chat(MODEL, messages, stream=True, temperature=0.6, on_chunk=_cb)
    except Exception as exc:
        logger.warning(f'[DeepSeekLocal] stream error: {exc}')
        return f'[deepseek-local] error: {exc}', 0

    logger.info(f'[DeepSeekLocal] model={MODEL} tokens={tokens}')
    return answer, tokens
