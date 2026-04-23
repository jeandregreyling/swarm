"""utils/coding_bible.py — Coding Bible loader.

Single source of truth: docs/CODING_BIBLE.md
- `quick_card()` returns the condensed rules block injected into coder agent
  system prompts. Cached for 30s so file edits show up without restart.
- `full_text()` returns the full Markdown body (used by the retrieval endpoint).
"""
from __future__ import annotations

import os
import re
import time
from typing import Tuple

_BIBLE_PATH = os.environ.get(
    'CODING_BIBLE_PATH',
    '/home/seven/swarm/docs/CODING_BIBLE.md',
)
_CACHE_TTL = 30.0

_cache: dict = {'mtime': 0.0, 'loaded_at': 0.0, 'full': '', 'quick': ''}


def _extract_quick_card(text: str) -> str:
    """Pull the fenced block that follows the 'Coder Persona Quick Card' heading."""
    m = re.search(
        r'## 10\.[^\n]*Quick Card[^\n]*\n+```([^\n]*)\n(.*?)```',
        text,
        re.DOTALL,
    )
    if m:
        return m.group(2).strip()
    return ''


def _load() -> Tuple[str, str]:
    """Return (full_text, quick_card). Cached, refreshed every TTL seconds."""
    try:
        st = os.stat(_BIBLE_PATH)
    except FileNotFoundError:
        return ('', '')
    now = time.time()
    if (
        _cache['full']
        and st.st_mtime == _cache['mtime']
        and (now - _cache['loaded_at']) < _CACHE_TTL
    ):
        return _cache['full'], _cache['quick']
    try:
        with open(_BIBLE_PATH, 'r', encoding='utf-8') as f:
            full = f.read()
    except OSError:
        return _cache['full'], _cache['quick']
    quick = _extract_quick_card(full)
    _cache.update(
        mtime=st.st_mtime, loaded_at=now, full=full, quick=quick,
    )
    return full, quick


def full_text() -> str:
    """Full Coding Bible Markdown."""
    return _load()[0]


def quick_card() -> str:
    """Condensed quick-card text for agent prompt injection."""
    return _load()[1]


def inject(prompt: str) -> str:
    """Prepend the quick-card to a system prompt if available."""
    qc = quick_card()
    if not qc:
        return prompt
    return f'{qc}\n\n{prompt}'
