"""
lib/knowledge/retrieval.py — Semantic search over embedded knowledge chunks.

Query flow:
  1. Embed the query string via Ollama nomic-embed-text
  2. Load all active chunks that have embeddings from the DB
  3. Rank by cosine similarity
  4. Deduplicate by source (return best chunk per source, then fill remaining slots)
  5. Falls back to keyword frequency match when Ollama is unavailable
"""

import json
import logging

logger = logging.getLogger('seven.knowledge.retrieval')


def _record_retrieval(query, results, *, agent=None, method='semantic'):
    try:
        from core.vortex_ledger import hash_context, record_action

        chunks = [
            {
                'chunk_id': str(chunk.get('chunk_id') or ''),
                'source_id': str(chunk.get('source_id') or ''),
                'title': str(chunk.get('title') or '')[:160],
                'category': str(chunk.get('category') or ''),
                'score': chunk.get('score'),
                'content_hash': hash_context(str(chunk.get('chunk_text') or '')),
            }
            for chunk in results
        ]
        record_action(
            'knowledge_retrieval',
            source_agent=agent or 'knowledge_retrieval',
            target_agent='knowledge_index',
            status='completed' if results else 'no_results',
            context_parts=(str(query or ''), [item['content_hash'] for item in chunks]),
            details={
                'method': method,
                'query_hash': hash_context(str(query or '')),
                'chunk_count': len(chunks),
                'chunks': chunks,
            },
            source='knowledge.retrieval',
        )
    except Exception:
        logger.exception('Could not record knowledge retrieval in Vortex')


def _cosine(a, b):
    try:
        import numpy as np
        a = np.array(a, dtype=float)
        b = np.array(b, dtype=float)
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.dot(a, b) / norm) if norm > 0 else 0.0
    except Exception:
        return 0.0


def search(query, top_k=6, deduplicate=True, category=None, agent=None):
    """
    Semantic search over the knowledge library.

    Returns a list of up to `top_k` dicts:
      {source_id, chunk_id, title, source_type, domain_tags, category, subcategory, chunk_text, score}

    `deduplicate=True` keeps only the highest-scoring chunk per source so
    results span multiple documents rather than repeating the same one.

    `category` scopes the search to a category and all its subcategories.
    """
    from lib.knowledge.store import get_all_chunks
    from lib.knowledge.ingest import embed_text

    chunks = get_all_chunks(category=category)
    if not chunks:
        _record_retrieval(query, [], agent=agent, method='empty')
        return []

    query_vec = embed_text(query)
    if query_vec is None:
        results = _keyword_search(query, chunks, top_k)
        _record_retrieval(query, results, agent=agent, method='keyword')
        return results

    scored = []
    for c in chunks:
        raw_emb = c.get('embedding')
        if not raw_emb:
            continue
        try:
            vec = json.loads(raw_emb) if isinstance(raw_emb, str) else raw_emb
            score = _cosine(query_vec, vec)
            scored.append({
                'source_id':   c['source_id'],
                'chunk_id':    c['chunk_id'],
                'title':       c['title'],
                'source_type': c['source_type'],
                'domain_tags': c['domain_tags'],
                'category':    c.get('category', 'general'),
                'subcategory': c.get('subcategory'),
                'chunk_text':  c['chunk_text'],
                'score':       round(score, 4),
            })
        except Exception:
            continue

    scored.sort(key=lambda x: x['score'], reverse=True)

    if deduplicate:
        seen = set()
        deduped = []
        for r in scored:
            sid = r['source_id']
            if sid not in seen:
                seen.add(sid)
                deduped.append(r)
            if len(deduped) >= top_k:
                break
        _record_retrieval(query, deduped, agent=agent)
        return deduped

    results = scored[:top_k]
    _record_retrieval(query, results, agent=agent)
    return results


def _keyword_search(query, chunks, top_k):
    """TF-style keyword fallback when Ollama embeddings are unavailable."""
    terms = [t for t in query.lower().split() if len(t) > 2]
    if not terms:
        return []

    scored = []
    for c in chunks:
        text_lower = c['chunk_text'].lower()
        hits = sum(text_lower.count(t) for t in terms)
        if hits:
            scored.append({
                'source_id':   c['source_id'],
                'chunk_id':    c['chunk_id'],
                'title':       c['title'],
                'source_type': c['source_type'],
                'domain_tags': c['domain_tags'],
                'chunk_text':  c['chunk_text'],
                'score':       round(hits / max(len(terms), 1), 4),
            })

    scored.sort(key=lambda x: x['score'], reverse=True)
    seen = set()
    results = []
    for r in scored:
        if r['source_id'] not in seen:
            seen.add(r['source_id'])
            results.append(r)
        if len(results) >= top_k:
            break
    return results
