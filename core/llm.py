"""
core/llm.py — Single Ollama gateway for the entire swarm.

This is the ONLY module in the repo that should import the `ollama` package.
All agents, pipelines, blueprints, and utilities must call the helpers here.

Why this exists
---------------
Before this module, ~15 files imported `ollama` directly. That made it
impossible to enforce:
  * a single `keep_alive` policy (had `-1` pins scattered across layers)
  * stream/block discipline (retries on stuck streams spawned double runners)
  * one log format for every request
  * per-model concurrency caps

Public API
----------
chat(model, messages, *, stream=False, temperature=None, keep_alive=None,
     options=None, on_chunk=None) -> (content: str, tokens: int)
ps() -> list[dict]
list_models() -> list[dict]
show(model) -> dict
embeddings(model, prompt) -> list[float]
pull(model, stream=True) -> iterator

Rules enforced
--------------
  * keep_alive: None/negative/zero → DEFAULT_KEEP_ALIVE (300s).
    A caller CANNOT request "Forever" ("-1"). That bug class is structurally
    impossible here.
  * Stream retries on failure are disallowed. If a stream raises, we return
    the partial content the caller already received. Re-calling ollama.chat
    on a stuck runner spawned a second runner that also hung — never again.
  * Every call emits one structured log line on exit (duration, tokens,
    model, stream/block).
  * Per-model concurrency: at most MAX_CONCURRENT_PER_MODEL active chats per
    model. Extra callers wait on a Semaphore rather than piling up runners.
"""

from __future__ import annotations

import logging
import json
import threading
import time
import urllib.request
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger('core.llm')

# ── Policy constants ────────────────────────────────────────────────────────
DEFAULT_KEEP_ALIVE = 300          # 5 minutes. Never pin forever.
MAX_CONCURRENT_PER_MODEL = 1      # One active chat per model — prevents double-runner spawn.
GATEWAY_CHAT_IDLE_TIMEOUT_S = 900
GATEWAY_CHAT_ABSOLUTE_TIMEOUT_S = 2000
_MODEL_LOCKS: dict[str, threading.Semaphore] = {}
_MODEL_LOCKS_MUTEX = threading.Lock()


def _lock_for(model: str) -> threading.Semaphore:
    with _MODEL_LOCKS_MUTEX:
        sem = _MODEL_LOCKS.get(model)
        if sem is None:
            sem = threading.Semaphore(MAX_CONCURRENT_PER_MODEL)
            _MODEL_LOCKS[model] = sem
        return sem


def _sanitize_keep_alive(value: Any) -> Any:
    """Force finite TTL. -1 / None / 0 → DEFAULT_KEEP_ALIVE.
    Ollama-style duration strings ('20m', '1h', '300s') pass through unchanged
    — Ollama parses them natively and they are always finite and positive.
    """
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ('', '-1', '0'):
            return DEFAULT_KEEP_ALIVE
        # Duration strings like '20m' / '1h' / '5s' / '300' are finite. Pass through.
        return s
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_KEEP_ALIVE
    if n <= 0:
        return DEFAULT_KEEP_ALIVE
    return n


def _get_ollama():
    """Lazy import so import failures surface at call time, not module load."""
    import ollama
    return ollama


def _to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_to_namespace(v) for v in value]
    return value


def _ollama_http(path: str) -> Any:
    with urllib.request.urlopen(f'http://localhost:11434{path}', timeout=5) as resp:
        return json.loads(resp.read().decode('utf-8') or '{}')


# ── Public API ──────────────────────────────────────────────────────────────

def chat(
    model: str,
    messages: list[dict],
    *,
    stream: bool = False,
    temperature: Optional[float] = None,
    keep_alive: Optional[int] = None,
    options: Optional[dict] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> tuple[str, int]:
    """
    Run an ollama chat completion under the shared policy.

    Returns (content, eval_count_tokens). Partial content is returned on
    stream errors — never raises a second ollama.chat call on failure.

    Set `stream=True` for incremental token output. `on_chunk(piece)` is
    called for every content chunk as it arrives.
    """
    ollama = _get_ollama()

    keep_alive = _sanitize_keep_alive(keep_alive if keep_alive is not None else DEFAULT_KEEP_ALIVE)

    opts: dict = dict(options or {})
    if temperature is not None and 'temperature' not in opts:
        opts['temperature'] = temperature

    sem = _lock_for(model)
    sem.acquire()
    t0 = time.monotonic()
    content_parts: list[str] = []
    tokens = 0
    mode = 'stream' if stream else 'block'
    error: Optional[str] = None

    try:
        if stream:
            try:
                resp_iter = ollama.chat(
                    model=model,
                    messages=messages,
                    options=opts,
                    keep_alive=keep_alive,
                    stream=True,
                )
                for chunk in resp_iter:
                    piece = (chunk.get('message') or {}).get('content') or ''
                    if piece:
                        content_parts.append(piece)
                        if on_chunk:
                            try:
                                on_chunk(piece)
                            except Exception:
                                pass
                    if chunk.get('done'):
                        tokens = int(chunk.get('eval_count') or 0)
            except Exception as exc:
                error = f'stream-error: {exc}'
                # Critical rule: NO blocking fallback. See module docstring.
                if not content_parts:
                    raise
        else:
            resp = ollama.chat(
                model=model,
                messages=messages,
                options=opts,
                keep_alive=keep_alive,
            )
            content_parts.append((resp.get('message') or {}).get('content') or '')
            tokens = int(resp.get('eval_count') or 0)

        return ''.join(content_parts), tokens
    finally:
        elapsed = time.monotonic() - t0
        sem.release()
        logger.info(
            '[llm] model=%s mode=%s elapsed=%.2fs tokens=%d chars=%d keep_alive=%ds%s',
            model, mode, elapsed, tokens, sum(len(p) for p in content_parts),
            keep_alive, f' error={error}' if error else '',
        )


def ps():
    """Return running models (raw ollama ListResponse; has `.models`)."""
    ollama = _get_ollama()
    if hasattr(ollama, 'ps'):
        return ollama.ps()
    data = _ollama_http('/api/ps')
    return SimpleNamespace(models=_to_namespace(data.get('models') or []))


def list_models():
    """Return all pulled models (raw ollama ListResponse; has `.models`)."""
    ollama = _get_ollama()
    if hasattr(ollama, 'list'):
        return ollama.list()
    data = _ollama_http('/api/tags')
    return SimpleNamespace(models=_to_namespace(data.get('models') or []))


def show(model: str):
    """Return metadata for a single model (raw ollama ShowResponse)."""
    return _get_ollama().show(model)


def embeddings(model: str, prompt: str) -> list[float]:
    """Return embeddings vector for prompt."""
    result = _get_ollama().embeddings(model=model, prompt=prompt)
    if isinstance(result, dict):
        return result.get('embedding', []) or []
    return getattr(result, 'embedding', []) or []


def pull(model: str, stream: bool = True) -> Iterable[dict]:
    """Pull (or update) a model; yields progress dicts when stream=True."""
    return _get_ollama().pull(model, stream=stream)


def chat_via_gateway(
    model: str,
    messages: list[dict],
    *,
    stage_cb: Optional[Callable[..., None]] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
    # Local chat jobs are surfaced through persistent job tracking after the
    # initial UI wait. Keep the gateway clocks aligned with that policy so a
    # healthy but slow local worker does not get killed by the lower transport
    # default while the chat layer still expects it to continue.
    idle_timeout_s: int = GATEWAY_CHAT_IDLE_TIMEOUT_S,
    absolute_timeout_s: int = GATEWAY_CHAT_ABSOLUTE_TIMEOUT_S,
    keep_alive: Any = None,
    options: Optional[dict] = None,
    temperature: Optional[float] = None,
) -> tuple[str, int]:
    """Stream a local Ollama chat through the Fridays runtime gateway.

    Returns the same `(content, tokens)` tuple as `chat()` so callers can swap
    in this helper without touching their downstream code, but every
    structured RuntimeEvent (queued / dispatch / first_token / token_heartbeat
    / completed / failed) is forwarded to `stage_cb` as a human-readable
    label. That gives the chat job stage_trace real idle/no-token clocks
    instead of the time-based heuristic.

    `stage_cb` is the same callback shape local agents already pass:
    `stage_cb(text, optional_extra)`. We tolerate either single-arg or
    two-arg implementations.
    """
    from core import model_runtime_gateway as _gw

    keep_alive_val = _sanitize_keep_alive(keep_alive if keep_alive is not None else DEFAULT_KEEP_ALIVE)
    if isinstance(keep_alive_val, str):
        keep_alive_arg: Any = keep_alive_val
        keep_alive_log = keep_alive_val
    else:
        keep_alive_arg = f"{int(keep_alive_val)}s"
        keep_alive_log = int(keep_alive_val)

    opts: dict = dict(options or {})
    if temperature is not None and 'temperature' not in opts:
        opts['temperature'] = temperature

    def _emit(text: str) -> None:
        if not callable(stage_cb):
            return
        try:
            stage_cb(text, None)
        except TypeError:
            try:
                stage_cb(text)
            except Exception:
                pass
        except Exception:
            pass

    def _on_event(event: dict) -> None:
        stage = str(event.get('stage') or '').strip()
        if not stage:
            return
        toks = int(event.get('tokens') or 0)
        detail = str(event.get('detail') or '')
        if stage == 'queued':
            _emit('gateway: queued')
        elif stage == 'dispatch':
            _emit(f'gateway: dispatch ({detail})' if detail else 'gateway: dispatch')
        elif stage == 'first_token':
            _emit(f'gateway: first token ({toks}t)')
        elif stage == 'token_heartbeat':
            _emit(f'gateway: heartbeat {toks}t')
        elif stage == 'completed':
            _emit(f'gateway: completed {toks}t')
        elif stage == 'failed':
            _emit(f'gateway: failed — {detail}' if detail else 'gateway: failed')
        else:
            _emit(f'gateway: {stage}')

    sem = _lock_for(model)
    sem.acquire()
    t0 = time.monotonic()
    error: Optional[str] = None
    result = None
    try:
        result = _gw.chat(
            model,
            messages,
            absolute_timeout_s=absolute_timeout_s,
            idle_timeout_s=idle_timeout_s,
            keep_alive=keep_alive_arg,
            options=opts,
            on_token=on_chunk,
            on_event=_on_event,
        )
        if not result.ok and not result.content:
            error = result.error or 'gateway error'
        return result.content or '', int(result.tokens or 0)
    finally:
        elapsed = time.monotonic() - t0
        sem.release()
        logger.info(
            '[llm.gateway] model=%s elapsed=%.2fs tokens=%d chars=%d keep_alive=%s%s',
            model,
            elapsed,
            int(getattr(result, 'tokens', 0) or 0),
            len(getattr(result, 'content', '') or ''),
            keep_alive_log,
            f' error={error}' if error else '',
        )
