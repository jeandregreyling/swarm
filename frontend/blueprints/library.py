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
from services import require_auth

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
        order       = request.args.get('order', 'created')
        # `recent` is shorthand for "?order=updated&limit=N"
        recent_raw  = request.args.get('recent')
        limit_raw   = request.args.get('limit')
        limit = None
        if recent_raw:
            try:
                limit = max(1, min(int(recent_raw), 200))
                order = 'updated'
            except ValueError:
                limit = None
        elif limit_raw:
            try:
                limit = max(1, min(int(limit_raw), 1000))
            except ValueError:
                limit = None
        sources = list_sources(status=status, category=category,
                               subcategory=subcategory, order=order,
                               limit=limit)
        stats   = source_stats()
        return jsonify({'ok': True, 'sources': sources, 'stats': stats,
                        'tags': _SAP_TAGS})
    except Exception as exc:
        logger.exception('[Library] list sources')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/sources/<int:source_id>', methods=['DELETE'])
@require_auth
def api_library_delete(source_id, current_user=None):
    try:
        from lib.knowledge.store import delete_source
        delete_source(source_id)
        return jsonify({'ok': True})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/sources/<int:source_id>', methods=['GET'])
def api_library_source_get(source_id):
    """Return full source record (raw_text + metadata) for the Open modal."""
    try:
        from lib.knowledge.store import get_source
        src = get_source(source_id)
        if not src:
            return jsonify({'ok': False, 'error': 'Not found'}), 404
        return jsonify({'ok': True, 'source': src})
    except Exception as exc:
        logger.exception('[Library] source_get')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/sources/<int:source_id>', methods=['PATCH'])
def api_library_source_update(source_id):
    """Reclassify or rename a source. Body: { title?, category?, subcategory?, tags? }"""
    try:
        data = request.get_json(silent=True) or {}
        from lib.knowledge.store import update_source, get_source
        if not get_source(source_id):
            return jsonify({'ok': False, 'error': 'Not found'}), 404
        ok = update_source(
            source_id,
            title=data.get('title'),
            category=data.get('category'),
            subcategory=data.get('subcategory'),
            domain_tags=data.get('tags'),
        )
        return jsonify({'ok': True, 'updated': bool(ok)})
    except Exception as exc:
        logger.exception('[Library] source_update')
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
        # S-B6F548DCDD: reject non-string scalar fields rather than coerce.
        # Stringifying a list/dict produces "[...]" / "{...}" that downstream
        # parsers happily ingest, polluting the library.
        for field in ('type', 'title', 'content', 'added_by', 'category', 'subcategory'):
            v = data.get(field)
            if v is not None and not isinstance(v, str):
                return jsonify({'ok': False,
                                'error': f'{field} must be a string'}), 400
        if 'tags' in data and not isinstance(data.get('tags'), list):
            return jsonify({'ok': False, 'error': 'tags must be an array'}), 400
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
    Body JSON: { "collection": "sap_corner" | "programming" | "fridays" | "all" }

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


# ── Research Topics (idle-research interest nodes) ────────────────────────────

def _topics_owner():
    """Username the topics are filed under. Defaults to 'ghost' (primary user)."""
    return 'ghost'


@library_bp.route('/api/library/topics', methods=['GET'])
def api_library_topics_list():
    """List research topics (user_interests rows). Active + paused together, newest first."""
    try:
        from database import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id, topic, category, score, source, source_agent, active, "
                "       created_at, updated_at "
                "FROM user_interests WHERE username = ? "
                "ORDER BY active DESC, score DESC, id DESC",
                (_topics_owner(),),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            out.append({
                'id':           r['id'],
                'topic':        r['topic'],
                'category':     r['category'],
                'score':        r['score'],
                'source':       r['source'],
                'source_agent': r['source_agent'],
                'active':       bool(r['active']),
                'created_at':   r['created_at'],
                'updated_at':   r['updated_at'],
            })
        return jsonify({'ok': True, 'topics': out})
    except Exception as exc:
        logger.exception('[Library] topics list')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/topics', methods=['POST'])
def api_library_topics_add():
    """Add a new research topic.
    Body: { topic, category?, score?, source_agent? }
    Defaults: category='sap_corner', score=8.0, source='user', source_agent=''.
    Idempotent on (username, topic) — re-adding an existing topic reactivates it."""
    try:
        data  = request.get_json(silent=True) or {}
        topic = str(data.get('topic') or '').strip()[:100]
        if not topic:
            return jsonify({'ok': False, 'error': 'topic is required'}), 400
        category     = str(data.get('category') or 'sap_corner').strip() or 'sap_corner'
        score        = float(data.get('score') or 8.0)
        source_agent = str(data.get('source_agent') or '').strip().lower()

        from database import get_connection
        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM user_interests WHERE username = ? AND topic = ?",
                (_topics_owner(), topic),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE user_interests SET active = 1, score = ?, "
                    "category = ?, updated_at = datetime('now') WHERE id = ?",
                    (score, category, existing['id']),
                )
                tid = existing['id']
            else:
                cur = conn.execute(
                    "INSERT INTO user_interests "
                    "(username, topic, category, source, source_agent, score, active) "
                    "VALUES (?, ?, ?, 'user', ?, ?, 1)",
                    (_topics_owner(), topic, category, source_agent, score),
                )
                tid = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        return jsonify({'ok': True, 'id': tid, 'topic': topic})
    except Exception as exc:
        logger.exception('[Library] topics add')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/topics/<int:topic_id>', methods=['PATCH'])
def api_library_topics_update(topic_id):
    """Pause/resume/rescope a topic. Body may contain: active, score, category, topic."""
    try:
        data = request.get_json(silent=True) or {}
        fields = []
        params = []
        if 'active' in data:
            fields.append('active=?')
            params.append(1 if data.get('active') else 0)
        if 'score' in data:
            fields.append('score=?')
            params.append(float(data.get('score') or 0))
        if 'category' in data and data['category']:
            fields.append('category=?')
            params.append(str(data['category']).strip())
        if 'topic' in data and data['topic']:
            fields.append('topic=?')
            params.append(str(data['topic']).strip()[:100])
        if not fields:
            return jsonify({'ok': False, 'error': 'no fields to update'}), 400
        fields.append("updated_at=datetime('now')")
        params.append(topic_id)

        from database import get_connection
        conn = get_connection()
        try:
            conn.execute(
                f"UPDATE user_interests SET {', '.join(fields)} WHERE id=?", params,
            )
            conn.commit()
        finally:
            conn.close()
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception('[Library] topics update')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/topics/<int:topic_id>', methods=['DELETE'])
def api_library_topics_delete(topic_id):
    """Hard-delete a topic."""
    try:
        from database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM user_interests WHERE id=?", (topic_id,))
            conn.commit()
        finally:
            conn.close()
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception('[Library] topics delete')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── STEP-KC-TOPICS-HIVE-NAVIGATION-20260430 ─────────────────────────────────
# Unified hive-graph endpoint. Returns topics + recent library sources as
# nodes and links them through their category. The Hive Nodes popout, KC
# Library top-bar dropdowns, and Mind Map view can all pull from this one
# endpoint instead of stitching graphs ad-hoc per surface.
#
# `/api/hive/resolve?kind=topic&id=42` returns the canonical hive-node anchor
# (e.g. /hive-nodes#topic-42) the UI should navigate to so that document /
# source / topic clicks all land on the same node spine.

@library_bp.route('/api/hive/graph', methods=['GET'])
def api_hive_graph():
    """Return {nodes: [...], edges: [...]} merging topics and recent sources."""
    try:
        _init()
        recent = max(1, min(int(request.args.get('recent', 30)), 200))
        from lib.knowledge.store import list_sources
        sources = list_sources(status='active', order='updated', limit=recent)
        from database import get_connection
        conn = get_connection()
        try:
            try:
                topic_rows = conn.execute(
                    "SELECT id, topic, category, score, active FROM user_interests "
                    "WHERE owner=? ORDER BY active DESC, score DESC LIMIT 200",
                    (_topics_owner(),),
                ).fetchall()
            except Exception:
                topic_rows = []
        finally:
            conn.close()
        nodes = []
        edges = []
        for t in topic_rows or []:
            tid = t['id'] if hasattr(t, 'keys') else t[0]
            topic = t['topic'] if hasattr(t, 'keys') else t[1]
            category = (t['category'] if hasattr(t, 'keys') else t[2]) or 'general'
            score = (t['score'] if hasattr(t, 'keys') else t[3]) or 0
            active = (t['active'] if hasattr(t, 'keys') else t[4])
            nodes.append({
                'id': f'topic-{tid}',
                'kind': 'topic',
                'label': topic,
                'category': category,
                'score': float(score or 0),
                'active': bool(active),
                'href': f'/hive-nodes#topic-{tid}',
            })
        for s in sources or []:
            sid = s.get('source_id') or s.get('id')
            cat = s.get('category') or 'general'
            label = (s.get('title') or s.get('source_ref') or s.get('url') or f'source-{sid}')[:80]
            nodes.append({
                'id': f'source-{sid}',
                'kind': 'source',
                'label': label,
                'category': cat,
                'href': f'/hive-nodes#source-{sid}',
            })
            # Edge each source -> any topic with the same category.
            for t in topic_rows or []:
                tcat = (t['category'] if hasattr(t, 'keys') else t[2]) or 'general'
                if tcat and tcat == cat:
                    tid = t['id'] if hasattr(t, 'keys') else t[0]
                    edges.append({'from': f'source-{sid}', 'to': f'topic-{tid}', 'kind': 'category'})
        return jsonify({'ok': True, 'nodes': nodes, 'edges': edges,
                        'counts': {'topics': sum(1 for n in nodes if n['kind'] == 'topic'),
                                   'sources': sum(1 for n in nodes if n['kind'] == 'source'),
                                   'edges': len(edges)}})
    except Exception as exc:
        logger.exception('[Library] hive graph')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/hive/resolve', methods=['GET'])
def api_hive_resolve():
    """Map (kind, id) → canonical hive node href + label.

    kind ∈ {topic, source, document}. document is treated as an alias for
    source for now since library_sources already covers ingested documents.
    """
    kind = (request.args.get('kind') or '').strip().lower()
    raw_id = (request.args.get('id') or '').strip()
    if kind == 'document':
        kind = 'source'
    if kind not in {'topic', 'source'}:
        return jsonify({'ok': False, 'error': 'invalid kind'}), 400
    try:
        nid = int(raw_id)
    except ValueError:
        return jsonify({'ok': False, 'error': 'invalid id'}), 400
    try:
        from database import get_connection
        conn = get_connection()
        try:
            if kind == 'topic':
                row = conn.execute(
                    "SELECT id, topic, category FROM user_interests WHERE id=?",
                    (nid,),
                ).fetchone()
                if not row:
                    return jsonify({'ok': False, 'error': 'topic not found'}), 404
                return jsonify({
                    'ok': True,
                    'kind': 'topic',
                    'id': nid,
                    'label': row['topic'] if hasattr(row, 'keys') else row[1],
                    'category': (row['category'] if hasattr(row, 'keys') else row[2]) or 'general',
                    'href': f'/hive-nodes#topic-{nid}',
                })
            row = conn.execute(
                "SELECT source_id, title, source_ref, category FROM knowledge_sources WHERE source_id=?",
                (nid,),
            ).fetchone()
            if not row:
                return jsonify({'ok': False, 'error': 'source not found'}), 404
            return jsonify({
                'ok': True,
                'kind': 'source',
                'id': nid,
                'label': (row['title'] if hasattr(row, 'keys') else row[1]) or
                         (row['source_ref'] if hasattr(row, 'keys') else row[2]) or f'source-{nid}',
                'category': (row['category'] if hasattr(row, 'keys') else row[3]) or 'general',
                'href': f'/hive-nodes#source-{nid}',
            })
        finally:
            conn.close()
    except Exception as exc:
        logger.exception('[Library] hive resolve')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── STEP-KC-INTERESTS-GENERAL-KNOWLEDGE-SUGGESTIONS-20260430 ────────────────
# Suggest optional general-knowledge additions based on the existing topic set.
# Curated bidirectional adjacency map — kept deliberately small so suggestions
# are useful context without "creepy personalisation". Each suggestion ships
# with a `because` field so the UI can show *why* it was suggested.
_TOPIC_ADJACENCY = {
    # SAP / payroll
    'sap':                ['payroll compliance australia', 'employee data privacy', 'ABAP fundamentals'],
    'sap payroll':        ['ato single touch payroll', 'fair work act basics', 'payroll year-end checklist'],
    'sap hcm':            ['workforce analytics', 'employee lifecycle management', 'PCR debugging patterns'],
    'payroll':            ['ato single touch payroll', 'fair work act basics', 'superannuation guarantee'],
    # Music / creative
    'music creation':     ['music theory fundamentals', 'mixing & mastering basics', 'song structure patterns'],
    'lo-fi':              ['music theory fundamentals', 'sample-clearance basics', 'side-chain compression'],
    'synthwave':          ['analog synth signal flow', 'reverb & delay basics', '80s production techniques'],
    'songwriting':        ['lyric structure (verse/chorus/bridge)', 'rhyme scheme catalog'],
    # Visual art
    'visual art':         ['colour theory primer', 'composition rules of thirds', 'lighting reference packs'],
    'image generation':   ['prompt engineering for diffusion', 'colour theory primer', 'composition rules of thirds'],
    # ML / dev
    'huggingface':        ['transformer architectures explained', 'tokeniser tradeoffs', 'inference quantisation'],
    'github':             ['conventional commits', 'semantic versioning', 'GitHub Actions cookbook'],
    'python':             ['type hints & typing module', 'async/await basics', 'pytest fixtures cheat-sheet'],
    'flask':              ['blueprints & app-factory pattern', 'request context lifecycle'],
    # Personal productivity (only suggested if the user already opted in to one)
    'productivity':       ['note-taking systems (zettelkasten / PARA)', 'pomodoro variants'],
    'home automation':    ['mqtt fundamentals', 'home assistant addons primer'],
}


@library_bp.route('/api/library/topics/suggestions', methods=['GET'])
def api_library_topics_suggestions():
    """Return general-knowledge topic suggestions adjacent to the user's
    existing topics.

    Each suggestion is { topic, category, because } so the UI can render the
    rationale alongside an Approve/Ignore action. Suggestions never include
    PII or anything inferred from chat content — they're pure adjacency from
    the curated _TOPIC_ADJACENCY map. Existing topics (active + paused) are
    excluded so the list never re-suggests something already opted in.
    """
    try:
        from database import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT topic, category FROM user_interests WHERE username=?",
                (_topics_owner(),),
            ).fetchall()
        finally:
            conn.close()
        existing = {str(r['topic'] or '').strip().lower() for r in rows}
        out = []
        seen = set()
        for r in rows:
            seed = str(r['topic'] or '').strip().lower()
            adj = _TOPIC_ADJACENCY.get(seed)
            if not adj:
                # Loose match — substring contains/contained-by.
                for key, vals in _TOPIC_ADJACENCY.items():
                    if key in seed or seed in key:
                        adj = vals
                        break
            if not adj:
                continue
            for s in adj:
                key = s.lower()
                if key in existing or key in seen:
                    continue
                seen.add(key)
                out.append({
                    'topic':    s,
                    'category': str(r['category'] or 'general'),
                    'because':  f'adjacent to your topic "{r["topic"]}"',
                })
        # Cap to 6 — keeps the strip tidy and avoids overwhelming the user.
        return jsonify({'ok': True, 'suggestions': out[:6]})
    except Exception as exc:
        logger.exception('[Library] topic suggestions')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/library/topics/run/<int:topic_id>', methods=['POST'])
def api_library_topics_run_now(topic_id):
    """Kick off an immediate research session for a single topic (background thread)."""
    try:
        from database import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT topic FROM user_interests WHERE id=? AND active=1",
                (topic_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return jsonify({'ok': False, 'error': 'Topic not found or paused'}), 404
        topic_text = row['topic']

        def _run():
            try:
                from fridays.research_workflow import run_research
                run_research(topic_text, depth='standard', requesting_agent='scholar')
            except Exception as exc2:
                logger.error(f'[Library] topic run error topic={topic_text!r}: {exc2}')

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({'ok': True, 'queued': True, 'topic': topic_text})
    except Exception as exc:
        logger.exception('[Library] topics run')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Manual / Single-source help ───────────────────────────────────────────────
# B15: every '?' tooltip pulls from `manual_content.MANUAL`. Update once → all
# tiles update. Frontend calls /api/manual/<key> from openWindowHelp().

@library_bp.route('/api/manual', methods=['GET'])
def api_manual_list():
    try:
        from manual_content import list_manual_keys
        return jsonify({'ok': True, 'keys': list_manual_keys()})
    except Exception as exc:
        logger.exception('[Manual] list')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/manual/<key>', methods=['GET'])
def api_manual_get(key):
    try:
        from manual_content import get_manual
        entry = get_manual(key)
        if not entry:
            return jsonify({'ok': False, 'error': 'not_found', 'key': key}), 404
        return jsonify({'ok': True, 'key': key, 'title': entry.get('title', ''), 'body': entry.get('body', '')})
    except Exception as exc:
        logger.exception('[Manual] get')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Feeds (M13 follow-up) ─────────────────────────────────────────────────────
# Lightweight per-user feed storage so Scholar/Librarian can ingest the same
# list the UI shows. Persists JSON in sandpits/<user>/feeds.json.

import json as _feeds_json
from pathlib import Path as _FeedsPath


def _feeds_path():
    base = _FeedsPath(__file__).resolve().parents[2] / 'sandpits' / 'seven'
    base.mkdir(parents=True, exist_ok=True)
    return base / 'feeds.json'


@library_bp.route('/api/feeds', methods=['GET'])
def api_feeds_get():
    try:
        p = _feeds_path()
        if not p.exists():
            return jsonify({'ok': True, 'feeds': {}})
        return jsonify({'ok': True, 'feeds': _feeds_json.loads(p.read_text() or '{}')})
    except Exception as exc:
        logger.exception('[Feeds] get')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@library_bp.route('/api/feeds', methods=['PUT'])
def api_feeds_put():
    try:
        payload = request.get_json(silent=True) or {}
        feeds = payload.get('feeds') or {}
        if not isinstance(feeds, dict):
            return jsonify({'ok': False, 'error': 'feeds must be an object'}), 400
        # Basic shape validation
        clean = {}
        for key, v in list(feeds.items())[:200]:
            if not isinstance(v, dict):
                continue
            clean[str(key)[:256]] = {
                'type': str(v.get('type') or 'provider')[:32],
                'url': str(v.get('url') or '')[:1024],
                'label': str(v.get('label') or '')[:256],
                'status': str(v.get('status') or 'connected')[:32],
                'added': int(v.get('added') or 0),
            }
        p = _feeds_path()
        p.write_text(_feeds_json.dumps(clean, indent=2))
        return jsonify({'ok': True, 'count': len(clean)})
    except Exception as exc:
        logger.exception('[Feeds] put')
        return jsonify({'ok': False, 'error': str(exc)}), 500
