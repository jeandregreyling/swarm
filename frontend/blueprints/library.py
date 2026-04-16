"""
frontend/blueprints/library.py — Knowledge Library API routes.

Handles ingestion (text, URL, email, PDF upload), semantic search,
source listing, deletion, and re-processing.  All heavy work (embedding)
is dispatched to a daemon thread so HTTP responses are non-blocking.

Categories: sap_corner, programming, fridays, general (with subcategories).
Agent context injection via /api/library/context.
Dedup via content_hash.
"""

import json
import logging
import sys
import threading
from pathlib import Path

from flask import Blueprint, request, jsonify

logger = logging.getLogger('seven.library')

_SWARM_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SWARM_ROOT / 'utils'))
sys.path.insert(0, str(_SWARM_ROOT))

library_bp = Blueprint('library', __name__)

_SAP_TAGS = [
    'sap_hcm', 'abap', 'payroll', 'sap_note',
    'ecp', 'btp', 'schema', 'pcr', 'infotype',
    'consulting', 'client', 'legal', 'process', 'project',
]


def _init():
    from lib.knowledge.store import ensure_schema
    ensure_schema()


# ── Sources ───────────────────────────────────────────────────────────────────

@library_bp.route('/api/library/sources', methods=['GET'])
def api_library_sources():
    try:
        _init()
        from lib.knowledge.store import list_sources, source_stats
        status      = request.args.get('status', 'active')
        category    = request.args.get('category') or None
        subcategory = request.args.get('subcategory') or None
        sources = list_sources(status=status, category=category,
                               subcategory=subcategory)
        stats   = source_stats()
        return jsonify({'ok': True, 'sources': sources, 'stats': stats,
                        'tags': _SAP_TAGS})
    except Exception as exc:
        logger.exception('[Library] list sources')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/sources/<int:source_id>', methods=['DELETE'])
def api_library_delete(source_id):
    try:
        from lib.knowledge.store import delete_source
        delete_source(source_id)
        return jsonify({'ok': True})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/sources/<int:source_id>/reprocess', methods=['POST'])
def api_library_reprocess(source_id):
    """Re-embed a source (useful after pulling nomic-embed-text for the first time)."""
    try:
        from lib.knowledge.store import get_source
        src = get_source(source_id)
        if not src:
            return jsonify({'ok': False, 'error': 'Not found'}), 404

        def _run():
            from lib.knowledge.ingest import process_source
            process_source(source_id, src.get('raw_text') or '')

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({'ok': True, 'queued': True})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Ingest ────────────────────────────────────────────────────────────────────

@library_bp.route('/api/library/ingest', methods=['POST'])
def api_library_ingest():
    """
    Ingest a text / URL / raw-email source.
    Body JSON:
      type        : 'text' | 'url' | 'email'
      title       : str (optional — auto-derived if missing)
      content     : str — the raw content or URL
      tags        : [str]
      added_by    : str (default 'ghost')
      category    : str (default 'general')
      subcategory : str (optional)
    """
    try:
        _init()
        data        = request.get_json(silent=True) or {}
        src_type    = (data.get('type') or 'text').strip().lower()
        title       = (data.get('title') or '').strip()
        content     = (data.get('content') or '').strip()
        tags        = data.get('tags') or []
        added_by    = (data.get('added_by') or 'ghost').strip()
        category    = (data.get('category') or 'general').strip()
        subcategory = (data.get('subcategory') or '').strip() or None

        if not content:
            return jsonify({'ok': False, 'error': 'content is required'}), 400

        raw_text   = content
        source_ref = None

        if src_type == 'url':
            source_ref = content
            if not title:
                title = content[:80]
            from lib.knowledge.sources.url_fetcher import extract as _url
            raw_text = _url(content)
            if raw_text.startswith('[URL fetch failed]'):
                return jsonify({'ok': False, 'error': raw_text}), 400

        elif src_type == 'email':
            from lib.knowledge.sources.email_parser import extract as _email
            derived_title, raw_text = _email(content)
            if not title:
                title = derived_title

        else:  # text
            from lib.knowledge.sources.text_parser import extract as _text
            raw_text = _text(content)

        if not title:
            title = raw_text[:60].replace('\n', ' ')

        # Dedup check
        from lib.knowledge.store import add_source, check_duplicate
        existing = check_duplicate(raw_text)
        if existing:
            return jsonify({'ok': False, 'error': 'Duplicate content — already exists as source #' + str(existing),
                            'duplicate_source_id': existing}), 409

        source_id = add_source(
            title=title, source_type=src_type, raw_text=raw_text,
            source_ref=source_ref, domain_tags=tags, added_by=added_by,
            category=category, subcategory=subcategory,
        )

        def _embed():
            try:
                from lib.knowledge.ingest import process_source
                process_source(source_id, raw_text)
            except Exception as exc2:
                logger.error(f'[Library] embed error source={source_id}: {exc2}')

        threading.Thread(target=_embed, daemon=True).start()

        return jsonify({'ok': True, 'source_id': source_id, 'title': title})

    except Exception as exc:
        logger.exception('[Library] ingest')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/ingest-pdf', methods=['POST'])
def api_library_ingest_pdf():
    """
    Multipart upload: file=<pdf>, title=<str>, tags=<json array>, added_by=<str>,
                      category=<str>, subcategory=<str>
    """
    try:
        _init()
        if 'file' not in request.files:
            return jsonify({'ok': False, 'error': 'No file provided'}), 400

        pdf_file    = request.files['file']
        title       = (request.form.get('title') or pdf_file.filename or 'PDF Document').strip()
        tags        = json.loads(request.form.get('tags', '[]') or '[]')
        added_by    = (request.form.get('added_by') or 'ghost').strip()
        category    = (request.form.get('category') or 'general').strip()
        subcategory = (request.form.get('subcategory') or '').strip() or None

        from lib.knowledge.sources.pdf_parser import extract_from_bytes
        derived_title, raw_text = extract_from_bytes(pdf_file.read())
        if not title or title == 'PDF Document':
            title = derived_title or pdf_file.filename or 'PDF Document'

        # Dedup
        from lib.knowledge.store import add_source, check_duplicate
        existing = check_duplicate(raw_text)
        if existing:
            return jsonify({'ok': False, 'error': 'Duplicate content — already exists as source #' + str(existing),
                            'duplicate_source_id': existing}), 409

        source_id = add_source(
            title=title, source_type='pdf', raw_text=raw_text,
            source_ref=pdf_file.filename, domain_tags=tags, added_by=added_by,
            category=category, subcategory=subcategory,
        )

        def _embed():
            try:
                from lib.knowledge.ingest import process_source
                process_source(source_id, raw_text)
            except Exception as exc2:
                logger.error(f'[Library] pdf embed error source={source_id}: {exc2}')

        threading.Thread(target=_embed, daemon=True).start()

        return jsonify({'ok': True, 'source_id': source_id, 'title': title})

    except Exception as exc:
        logger.exception('[Library] ingest-pdf')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Search ────────────────────────────────────────────────────────────────────

@library_bp.route('/api/library/search', methods=['GET'])
def api_library_search():
    """
    GET /api/library/search?q=<query>&k=<top_k>&category=<cat>
    Returns ranked list of chunks with source metadata.
    """
    query    = (request.args.get('q') or '').strip()
    top_k    = min(int(request.args.get('k', 8)), 20)
    category = request.args.get('category') or None
    if not query:
        return jsonify({'ok': False, 'error': 'q parameter is required'}), 400
    try:
        from lib.knowledge.retrieval import search
        results = search(query, top_k=top_k, category=category)
        return jsonify({'ok': True, 'results': results, 'query': query})
    except Exception as exc:
        logger.exception('[Library] search')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Ollama model pull ─────────────────────────────────────────────────────────

@library_bp.route('/api/library/pull-model', methods=['POST'])
def api_library_pull_model():
    """
    Trigger an Ollama pull for nomic-embed-text (only needed once).
    Non-blocking — returns immediately; pull happens in background.
    """
    def _pull():
        try:
            import requests as _req
            _req.post(
                'http://localhost:11434/api/pull',
                json={'name': 'nomic-embed-text'},
                timeout=600,
            )
        except Exception as exc:
            logger.error(f'[Library] model pull error: {exc}')

    threading.Thread(target=_pull, daemon=True).start()
    return jsonify({'ok': True, 'message': 'Pulling nomic-embed-text in background…'})


@library_bp.route('/api/library/model-status', methods=['GET'])
def api_library_model_status():
    """Check whether nomic-embed-text is available."""
    try:
        from lib.knowledge.ingest import check_model_available
        ready = check_model_available()
        return jsonify({'ok': True, 'ready': ready, 'model': 'nomic-embed-text'})
    except Exception as exc:
        return jsonify({'ok': False, 'ready': False, 'error': str(exc)})


# ── Categories ────────────────────────────────────────────────────────────────

@library_bp.route('/api/library/categories', methods=['GET'])
def api_library_categories():
    """Return the full category tree for the UI."""
    try:
        from lib.knowledge.categories import tree_json
        from lib.knowledge.store import source_stats
        _init()
        stats = source_stats()
        return jsonify({
            'ok': True,
            'categories': tree_json(),
            'by_category': stats.get('by_category', {}),
        })
    except Exception as exc:
        logger.exception('[Library] categories')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Agent context injection ───────────────────────────────────────────────────

@library_bp.route('/api/library/context', methods=['GET'])
def api_library_context():
    """
    GET /api/library/context?q=<query>&agent=<name>&category=<cat>&k=<top_k>

    Returns relevant knowledge chunks for an agent to inject into its context.
    Agents call this before responding to supplement their knowledge.

    The response includes a pre-formatted context block that agents can
    paste into their system/user prompt.
    """
    query    = (request.args.get('q') or '').strip()
    agent    = (request.args.get('agent') or '').strip()
    category = request.args.get('category') or None
    top_k    = min(int(request.args.get('k', 4)), 10)

    if not query:
        return jsonify({'ok': False, 'error': 'q required'}), 400

    try:
        _init()
        from lib.knowledge.retrieval import search

        # Auto-detect SAP context
        _SAP_KEYWORDS = {'sap', 'abap', 'payroll', 'infotype', 'schema', 'pcr',
                         'wage type', 'bapi', 'ecp', 'hcm', 'pa30', 'pa20',
                         'se38', 'sm37', 'pe51', 'pe03', 'pe01', 'pe02',
                         'processing class', 'retro', 'off-cycle'}
        query_lower = query.lower()
        if not category:
            if any(kw in query_lower for kw in _SAP_KEYWORDS):
                category = 'sap_corner'

        results = search(query, top_k=top_k, category=category)

        if not results:
            return jsonify({'ok': True, 'context': '', 'chunks': [], 'category_used': category})

        # Build a formatted context block for agent injection
        lines = [f'=== Library Knowledge ({category or "all"}) ===']
        for r in results:
            lines.append(f'\n--- {r["title"]} [{r.get("category", "general")}] (score: {r["score"]}) ---')
            lines.append(r['chunk_text'][:800])
        lines.append('\n=== End Library Knowledge ===')

        return jsonify({
            'ok': True,
            'context': '\n'.join(lines),
            'chunks': results,
            'category_used': category,
        })
    except Exception as exc:
        logger.exception('[Library] context')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Seed ──────────────────────────────────────────────────────────────────────

@library_bp.route('/api/library/seed', methods=['POST'])
def api_library_seed():
    """
    POST /api/library/seed
    Body JSON: { "collection": "sap_corner" | "programming" | "all" }

    Seeds the library with built-in knowledge documents. Idempotent — skips
    documents whose content_hash already exists.
    """
    try:
        _init()
        data = request.get_json(silent=True) or {}
        collection = (data.get('collection') or 'all').strip()

        from lib.knowledge.seed import seed_collection
        added, skipped = seed_collection(collection)

        return jsonify({
            'ok': True,
            'added': added,
            'skipped': skipped,
            'message': f'Seeded {added} documents ({skipped} skipped as dupes)',
        })
    except Exception as exc:
        logger.exception('[Library] seed')
        return jsonify({'ok': False, 'error': str(exc)}), 500
