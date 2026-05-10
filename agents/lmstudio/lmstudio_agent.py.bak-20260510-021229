"""
agents/lmstudio/lmstudio_agent.py — LM Studio (local OpenAI-compatible)
Routes to whatever model is currently loaded in LM Studio (port 1234).
Falls back gracefully when LM Studio is not running.
"""
import logging, sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.lmstudio')
AGENT_NAME  = 'lmstudio'
_BASE_URL   = 'http://localhost:1234/v1'
_API_KEY    = 'lm-studio'

_SYSTEM_PROMPT = """You are an AI assistant running locally in LM Studio as part of Seven's Swarm.
Built for Ghost One (Jeandre) on a Dell OptiPlex 7090 in Melbourne, Australia.
You are fully offline — no data leaves this machine.
Be helpful, direct, and concise. Go directly to the answer."""


def _get_loaded_model(client):
    """Return the first model ID from LM Studio, or a fallback."""
    try:
        models = client.models.list()
        if models.data:
            return models.data[0].id
    except Exception:
        pass
    return 'local-model'


def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try:
                stage_cb(t, None)
            except Exception:
                pass

    try:
        from openai import OpenAI
    except ImportError:
        return '[lmstudio] openai package not installed', 0

    _emit('connecting to LM Studio')
    try:
        client = OpenAI(api_key=_API_KEY, base_url=_BASE_URL)
        model  = _get_loaded_model(client)
    except Exception as e:
        return f'[lmstudio] connection failed: {e}', 0

    if not model:
        return '[lmstudio] no model loaded in LM Studio — load a model first', 0

    _emit(f'dispatching to LM Studio · {model}')
    messages = [{'role': 'system', 'content': _SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-8:])
    messages.append({'role': 'user', 'content': message})

    try:
        # LM Studio supports streaming via the OpenAI SDK
        chunks = []
        token_count = 0
        stream = client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=2048, temperature=0.7, stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or '' if chunk.choices else ''
            if delta:
                chunks.append(delta)
                token_count += 1
                if token_count % 15 == 0:
                    _emit(f'generating · {("".join(chunks))[-300:]}')
        answer = ''.join(chunks)
        tokens = token_count  # approximate — LM Studio doesn't always return usage in stream
    except Exception as exc:
        logger.warning(f'[LMStudio] stream failed, trying blocking: {exc}')
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, max_tokens=2048, temperature=0.7,
            )
            answer = resp.choices[0].message.content
            tokens = resp.usage.total_tokens if resp.usage else 0
        except Exception as e:
            err = str(e)
            if 'connection' in err.lower() or 'refused' in err.lower():
                return '[lmstudio] LM Studio is not running — start it and load a model', 0
            return f'[lmstudio] error: {err}', 0

    logger.info(f'[LMStudio] model={model} tokens={tokens}')
    return answer, tokens
