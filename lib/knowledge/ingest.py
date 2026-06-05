"""
lib/knowledge/ingest.py — Text chunking and local embedding pipeline.

nomic-embed-text (fully local, no API cost) handles all embeddings. Seven
Runtime can serve it directly from GGUF, with Ollama kept as a compatibility
fallback. If embedding is unavailable, chunks are stored without vectors and
keyword search is used at query time.
"""

import re
import logging

logger = logging.getLogger('seven.knowledge.ingest')

CHUNK_SIZE    = 1800   # characters  (≈ 450 tokens — stays well within nomic's 8k limit)
CHUNK_OVERLAP = 200    # character overlap between consecutive chunks
OLLAMA_MODEL  = 'nomic-embed-text'


# ── Text chunking ─────────────────────────────────────────────────────────────

def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Split `text` into overlapping character-window chunks.
    Respects paragraph boundaries before falling back to sentence/word splits.
    Returns list of non-empty strings, each at least 50 chars.
    """
    text = (text or '').strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    chunks = []
    current = ''

    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + 2 + len(para) <= size:
            current += '\n\n' + para
        else:
            if current:
                chunks.append(current)
            # Paragraph itself too long → split at sentence boundaries
            if len(para) > size:
                parts = _split_long(para, size)
                chunks.extend(parts[:-1])
                current = parts[-1] if parts else ''
            else:
                # Start new chunk; carry a short overlap from previous
                tail = chunks[-1][-overlap:] if chunks and len(chunks[-1]) > overlap else (chunks[-1] if chunks else '')
                current = (tail + '\n\n' + para) if tail else para

    if current:
        chunks.append(current)

    return [c for c in chunks if len(c.strip()) >= 50]


def _split_long(text, size):
    """Split a long block at sentence boundaries, then word boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    parts, current = [], ''
    for s in sentences:
        if len(current) + len(s) + 1 <= size:
            current = (current + ' ' + s).strip() if current else s
        else:
            if current:
                parts.append(current)
            if len(s) > size:
                # Word-split as last resort
                for i in range(0, len(s), size):
                    parts.append(s[i:i + size])
                current = ''
            else:
                current = s
    if current:
        parts.append(current)
    return parts if parts else [text[:size]]


# ── Local embedding ───────────────────────────────────────────────────────────

def embed_text(text):
    """
    Embed `text` using the configured local nomic-embed-text path.
    Returns a list of floats, or None on failure.
    """
    try:
        from core import llm as _llm
        vec = _llm.embeddings(model=OLLAMA_MODEL, prompt=text)
        return vec or None
    except Exception as exc:
        logger.debug(f'[Ingest] local embed failed: {exc}')
        return None


def embed_batch(texts):
    """
    Embed a list of texts using the same local runtime path as embed_text().
    Returns a list of vectors; None entries mean embedding failed.
    """
    if not texts:
        return []
    return [embed_text(t) for t in texts]


def check_model_available():
    """Return True if nomic-embed-text is available directly or via Ollama."""
    try:
        from core import llm as _llm
        direct = getattr(_llm, '_direct_embedding_model')('nomic-embed-text')
        if direct:
            return True
    except Exception:
        pass
    try:
        from core import llm as _llm
        models = _llm.list_models()
        names = [
            (getattr(m, 'model', None) or getattr(m, 'name', '') or '').lower()
            for m in (models.models if hasattr(models, 'models') else [])
        ]
        return any(OLLAMA_MODEL in n for n in names)
    except Exception:
        return False


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_source(source_id, raw_text):
    """
    Chunk raw_text → embed all chunks in parallel → persist to DB.
    Returns (chunk_count: int, error: str | None).
    """
    from lib.knowledge.store import save_chunks

    chunks = chunk_text(raw_text)
    if not chunks:
        return 0, 'No usable text extracted'

    vectors      = embed_batch(chunks)
    pairs        = list(zip(chunks, vectors))
    failed_embeds = sum(1 for _, v in pairs if v is None)

    save_chunks(source_id, pairs)
    embedded = len(pairs) - failed_embeds
    logger.info(
        f'[Ingest] source={source_id} chunks={len(chunks)} embedded={embedded} '
        f'({"ok" if not failed_embeds else f"{failed_embeds} without vector"})'
    )
    return len(chunks), None
