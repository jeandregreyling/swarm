"""kb.py — Knowledge Base routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

kb_bp = Blueprint('kb', __name__)

def _ensure_project_doc_versions_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_doc_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER,
            doc_name TEXT,
            content TEXT,
            tags TEXT,
            version_number INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            source TEXT DEFAULT 'terminal_ui'
        )
        """
    )



def _next_project_doc_version(conn, doc_id):
    row = conn.execute(
        'SELECT COALESCE(MAX(version_number), 0) AS v FROM project_doc_versions WHERE doc_id=?',
        (doc_id,)
    ).fetchone()
    return int((row['v'] if row else 0) or 0) + 1



def _record_project_doc_version(conn, doc_id, doc_name, content, tags, action, source='terminal_ui'):
    _ensure_project_doc_versions_schema(conn)
    version = _next_project_doc_version(conn, doc_id)
    conn.execute(
        """
        INSERT INTO project_doc_versions
        (doc_id, doc_name, content, tags, version_number, action, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, doc_name, content, tags, version, action, source)
    )
    return version


@kb_bp.route('/api/kb')
def api_kb_list():
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    rows = conn.execute(
        """
        SELECT d.id,
               d.doc_name,
               d.tags,
               d.updated_at,
               LENGTH(COALESCE(d.content, '')) AS content_length,
               COALESCE(v.version_count, 0) AS version_count
        FROM project_docs d
        LEFT JOIN (
            SELECT doc_id, COUNT(*) AS version_count
            FROM project_doc_versions
            GROUP BY doc_id
        ) v ON v.doc_id = d.id
        ORDER BY d.updated_at DESC
        """
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])



@kb_bp.route('/api/kb/<int:doc_id>')
def api_kb_get(doc_id):
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    row = conn.execute('SELECT * FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))



@kb_bp.route('/api/kb/<int:doc_id>/versions')
def api_kb_versions(doc_id):
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    exists = conn.execute('SELECT id FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    versions = conn.execute(
        """
        SELECT id, doc_id, doc_name, tags, version_number, action, created_at, source,
               LENGTH(COALESCE(content, '')) AS content_length
        FROM project_doc_versions
        WHERE doc_id=?
        ORDER BY version_number DESC, id DESC
        """,
        (doc_id,)
    ).fetchall()
    conn.close()

    if not exists and not versions:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True, 'versions': [dict(v) for v in versions]})



@kb_bp.route('/api/kb/<int:doc_id>/restore', methods=['POST'])
def api_kb_restore(doc_id):
    data = request.get_json() or {}
    version_id = data.get('version_id')
    if version_id is None:
        return jsonify({'ok': False, 'error': 'version_id required'}), 400

    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    version = conn.execute(
        'SELECT * FROM project_doc_versions WHERE id=? AND doc_id=?',
        (int(version_id), doc_id)
    ).fetchone()
    if not version:
        conn.close()
        return jsonify({'ok': False, 'error': 'version not found'}), 404

    row = conn.execute('SELECT id FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE project_docs SET doc_name=?, content=?, tags=?, updated_at=datetime('now') WHERE id=?",
            (version['doc_name'], version['content'], version['tags'], doc_id)
        )
    else:
        conn.execute(
            "INSERT INTO project_docs (id, doc_name, content, tags, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (doc_id, version['doc_name'], version['content'], version['tags'])
        )

    _record_project_doc_version(
        conn,
        doc_id=doc_id,
        doc_name=version['doc_name'],
        content=version['content'],
        tags=version['tags'],
        action='restore',
        source='terminal_ui',
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



@kb_bp.route('/api/kb', methods=['POST'])
def api_kb_create():
    data     = request.get_json() or {}
    doc_name = (data.get('doc_name') or '').strip()
    content  = (data.get('content') or '').strip()
    tags     = (data.get('tags') or 'all').strip()
    if not doc_name:
        return jsonify({'error': 'doc_name required'}), 400
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    cur = conn.execute(
        "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
        (doc_name, content, tags)
    )
    new_id = cur.lastrowid
    _record_project_doc_version(
        conn,
        doc_id=new_id,
        doc_name=doc_name,
        content=content,
        tags=tags,
        action='create',
        source='terminal_ui',
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'id': new_id})



@kb_bp.route('/api/kb/<int:doc_id>', methods=['PUT'])
def api_kb_update(doc_id):
    data     = request.get_json() or {}
    doc_name = (data.get('doc_name') or '').strip()
    content  = (data.get('content') or '').strip()
    tags     = (data.get('tags') or 'all').strip()
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    existing = conn.execute('SELECT id FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'ok': False, 'error': 'not found'}), 404
    conn.execute(
        "UPDATE project_docs SET doc_name=?, content=?, tags=?, updated_at=datetime('now') WHERE id=?",
        (doc_name, content, tags, doc_id)
    )
    _record_project_doc_version(
        conn,
        doc_id=doc_id,
        doc_name=doc_name,
        content=content,
        tags=tags,
        action='update',
        source='terminal_ui',
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



@kb_bp.route('/api/kb/<int:doc_id>', methods=['DELETE'])
def api_kb_delete(doc_id):
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    row = conn.execute('SELECT id, doc_name, content, tags FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'not found'}), 404

    _record_project_doc_version(
        conn,
        doc_id=row['id'],
        doc_name=row['doc_name'],
        content=row['content'],
        tags=row['tags'],
        action='delete',
        source='terminal_ui',
    )
    conn.execute('DELETE FROM project_docs WHERE id=?', (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



