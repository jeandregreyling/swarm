"""
core/chunk/quintum.py — Quintum chunking for small-model Studio task delegation.

Splits a text into focused chunks that a 7B local model can grip in a single
pass.  The five-part cycle this feeds into is:

    split → probe → note → synthesise → validate

Splitting strategy (priority order):
  1. Blank-line-separated paragraphs / headings / list blocks.
  2. Sentence boundaries ('. ', '! ', '? ').
  3. Hard word-count split as a last resort.

Chunks are never split mid-sentence unless a single sentence exceeds
*max_tokens* by itself (in which case it is split at the token boundary as a
last resort).

Token estimation: 1 token ≈ 4 characters (conservative approximation that
avoids a hard dependency on a tokenizer).
"""

from __future__ import annotations

import re
from typing import List

_CHARS_PER_TOKEN = 4  # conservative approximation

# Patterns that indicate a logical block boundary.
_HEADING_RE = re.compile(r'^#{1,6}\s', re.MULTILINE)
_BLANK_LINE_RE = re.compile(r'\n\s*\n')

# Sentence-ending punctuation followed by whitespace or end-of-string.
_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+')


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_into_paragraphs(text: str) -> List[str]:
    """Split on blank lines; also treat heading lines as natural boundaries."""
    # Inject a virtual blank line before every heading so headings start chunks.
    text = _HEADING_RE.sub(lambda m: '\n\n' + m.group(0), text)
    parts = _BLANK_LINE_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_into_sentences(text: str) -> List[str]:
    parts = _SENTENCE_END_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def chunk_split(text: str, max_tokens: int = 800) -> List[str]:
    """Split *text* into chunks of at most *max_tokens* each.

    Returns a list of non-empty strings.  The original content is never
    altered — only split points are chosen.

    Args:
        text:       The full text to split (step description, Blackboard
                    context, etc.).
        max_tokens: Soft upper bound per chunk in tokens (1 token ≈ 4 chars).
                    Values below 50 are silently raised to 50.

    Returns:
        List of chunk strings, each under *max_tokens* (best-effort; a single
        sentence that exceeds the limit is returned as its own chunk).
    """
    max_tokens = max(50, max_tokens)
    max_chars = max_tokens * _CHARS_PER_TOKEN
    text = (text or '').strip()
    if not text:
        return []

    # Fast path: fits in one chunk.
    if _estimate_tokens(text) <= max_tokens:
        return [text]

    chunks: List[str] = []
    current_parts: List[str] = []
    current_chars = 0

    def _flush():
        if current_parts:
            chunks.append('\n\n'.join(current_parts))
            current_parts.clear()

    paragraphs = _split_into_paragraphs(text)

    for para in paragraphs:
        para_chars = len(para)

        if para_chars <= max_chars:
            # Para fits whole.
            if current_chars + para_chars > max_chars and current_parts:
                _flush()
                current_chars = 0
            current_parts.append(para)
            current_chars += para_chars
        else:
            # Para too big — split into sentences.
            if current_parts:
                _flush()
                current_chars = 0
            sentences = _split_into_sentences(para)
            for sent in sentences:
                sent_chars = len(sent)
                if sent_chars <= max_chars:
                    if current_chars + sent_chars > max_chars and current_parts:
                        _flush()
                        current_chars = 0
                    current_parts.append(sent)
                    current_chars += sent_chars
                else:
                    # Single sentence exceeds limit — hard-split by characters.
                    if current_parts:
                        _flush()
                        current_chars = 0
                    for i in range(0, sent_chars, max_chars):
                        chunks.append(sent[i:i + max_chars])

    _flush()
    return [c for c in chunks if c.strip()]


def chunk_with_context(
    text: str,
    context_prefix: str = '',
    max_tokens: int = 800,
    context_budget: float = 0.25,
) -> List[str]:
    """Split *text* into chunks, prepending a shared *context_prefix* to each.

    *context_budget* controls what fraction of *max_tokens* the prefix may
    consume (default 25%).  The remainder is available for the chunk body.

    Useful when the step description should be paired with a small amount of
    project context on every probe pass.
    """
    if not context_prefix:
        return chunk_split(text, max_tokens=max_tokens)

    prefix_tokens = _estimate_tokens(context_prefix)
    body_tokens = max(50, int(max_tokens * (1 - context_budget)) - prefix_tokens)
    body_chunks = chunk_split(text, max_tokens=body_tokens)
    sep = '\n\n---\n\n'
    return [context_prefix + sep + chunk for chunk in body_chunks]
