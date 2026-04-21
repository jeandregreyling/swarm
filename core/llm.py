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
import threading
import time
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger('core.llm')

# ── Policy constants ────────────────────────────────────────────────────────
DEFAULT_KEEP_ALIVE = 300          # 5 minutes. Never pin forever.
MAX_CONCURRENT_PER_MODEL = 1      # One active chat per model — prevents double-runner spawn.
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


def ps() -> list[dict]:
    """Return currently loaded models (thin passthrough)."""
    result = _get_ollama().ps()
    return result.get('models', []) if isinstance(result, dict) else getattr(result, 'models', [])


def list_models() -> list[dict]:
    """Return all pulled models (thin passthrough)."""
    result = _get_ollama().list()
    return result.get('models', []) if isinstance(result, dict) else getattr(result, 'models', [])


def show(model: str) -> dict:
    """Return metadata for a single model."""
    result = _get_ollama().show(model)
    return result if isinstance(result, dict) else dict(result)


def embeddings(model: str, prompt: str) -> list[float]:
    """Return embeddings vector for prompt."""
    result = _get_ollama().embeddings(model=model, prompt=prompt)
    if isinstance(result, dict):
        return result.get('embedding', []) or []
    return getattr(result, 'embedding', []) or []


def pull(model: str, stream: bool = True) -> Iterable[dict]:
    """Pull (or update) a model; yields progress dicts when stream=True."""
    return _get_ollama().pull(model, stream=stream)
