"""utils/coding_bible.py — Coding Bible loader.

Single source of truth: Studio `project_docs.doc_name = 'docs/CODING_BIBLE.md'`.
PACKET-01 moved doc-class .md files into Studio; the disk file at
``docs/CODING_BIBLE.md`` now contains only a redirect stub. The loader
prefers Studio and falls back to the disk file only if Studio has no row
and the disk file isn't a redirect stub (legacy installs).

- `quick_card()` returns the condensed rules block injected into coder agent
  system prompts. Cached for 30s so edits show up without restart.
- `full_text()` returns the full Markdown body (used by the retrieval endpoint).
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from typing import Tuple

_BIBLE_PATH = os.environ.get(
    'CODING_BIBLE_PATH',
    '/home/seven/swarm/docs/CODING_BIBLE.md',
)
_DB_PATH = os.environ.get(
    'SWARM_MEMORY_DB',
    '/home/seven/swarm/swarm_memory.db',
)
_DOC_NAME = 'docs/CODING_BIBLE.md'
_CACHE_TTL = 30.0
# Disk redirect stubs left after PACKET-01 contain this marker.
_REDIRECT_MARKER = 'Moved into Studio'

_cache: dict = {'mtime': 0.0, 'loaded_at': 0.0, 'full': '', 'quick': '', 'src': ''}


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


def _load_from_studio() -> str:
    """Return Studio's bible content, or '' if unavailable."""
    try:
        con = sqlite3.connect(_DB_PATH)
        try:
            row = con.execute(
                "SELECT content, updated_at FROM project_docs WHERE doc_name = ?",
                (_DOC_NAME,),
            ).fetchone()
        finally:
            con.close()
    except Exception:
        return ''
    if not row:
        return ''
    content = (row[0] or '').strip()
    if not content or _REDIRECT_MARKER in content[:200]:
        return ''
    return content


def _load_from_disk() -> Tuple[str, float]:
    """Return (text, mtime) from the disk file, ignoring redirect stubs."""
    try:
        st = os.stat(_BIBLE_PATH)
    except FileNotFoundError:
        return ('', 0.0)
    try:
        with open(_BIBLE_PATH, 'r', encoding='utf-8') as f:
            full = f.read()
    except OSError:
        return ('', st.st_mtime)
    if _REDIRECT_MARKER in full[:200]:
        return ('', st.st_mtime)
    return (full, st.st_mtime)


def _load() -> Tuple[str, str]:
    """Return (full_text, quick_card). Studio first, disk fallback. Cached."""
    now = time.time()
    if _cache['full'] and (now - _cache['loaded_at']) < _CACHE_TTL:
        return _cache['full'], _cache['quick']

    full = _load_from_studio()
    src = 'studio'
    mtime = 0.0
    if not full:
        full, mtime = _load_from_disk()
        src = 'disk'
    if not full:
        return _cache['full'], _cache['quick']  # last-known good

    quick = _extract_quick_card(full)
    _cache.update(
        mtime=mtime, loaded_at=now, full=full, quick=quick, src=src,
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
