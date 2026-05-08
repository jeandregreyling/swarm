"""media_curriculum.py — KC media topic ↔ tool curriculum + provenance.

STEP-KC-MEDIA-TOOL-LEARNING-CURRICULUM-20260430.

Connects music, image, video, style, genre, and production topics to the
tools agents use, so generated media has traceable learning/source context.

Two surfaces:

* `kc_media_curriculum` — topic/kind ↔ tool mapping with optional notes. The
  curriculum is the "what should agents reach for when working on X" lookup
  the chat surfaces and Media Center can consult before generation.

* `kc_media_trace` — per-asset provenance row recording which curriculum
  rows (topics + tools) were active when the asset was generated, plus a
  reference back to the originating Studio project. This is what makes the
  step's promise of "traceable learning/source context" real.

Both tables are created idempotently on first call to `_ensure_schema()`.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

from flask import Blueprint, request, jsonify

from services import get_connection

media_curriculum_bp = Blueprint('media_curriculum', __name__)

_VALID_KINDS = {'music', 'image', 'video', 'style', 'genre', 'production', 'app', 'game'}


def _ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS kc_media_curriculum (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            kind  TEXT NOT NULL,
            tool  TEXT NOT NULL,
            notes TEXT,
            created_at REAL NOT NULL,
            UNIQUE(topic, kind, tool)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS kc_media_trace (
            trace_id    TEXT PRIMARY KEY,
            asset_id    TEXT NOT NULL,
            project_id  TEXT,
            topics_json TEXT NOT NULL,
            tools_json  TEXT NOT NULL,
            agent       TEXT,
            created_at  REAL NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kc_media_trace_asset ON kc_media_trace(asset_id)"
    )


@media_curriculum_bp.route('/api/kc/media/curriculum', methods=['GET'])
def list_curriculum():
    kind = (request.args.get('kind') or '').strip().lower() or None
    if kind and kind not in _VALID_KINDS:
        return jsonify({'ok': False, 'error': f'invalid kind: {kind}'}), 400
    conn = get_connection()
    try:
        _ensure_schema(conn)
        if kind:
            rows = conn.execute(
                "SELECT id, topic, kind, tool, notes, created_at FROM kc_media_curriculum "
                "WHERE kind=? ORDER BY topic, tool",
                (kind,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, topic, kind, tool, notes, created_at FROM kc_media_curriculum "
                "ORDER BY kind, topic, tool"
            ).fetchall()
        items = []
        for r in rows:
            items.append({
                'id':    r['id']    if hasattr(r, 'keys') else r[0],
                'topic': r['topic'] if hasattr(r, 'keys') else r[1],
                'kind':  r['kind']  if hasattr(r, 'keys') else r[2],
                'tool':  r['tool']  if hasattr(r, 'keys') else r[3],
                'notes': (r['notes'] if hasattr(r, 'keys') else r[4]) or '',
                'created_at': r['created_at'] if hasattr(r, 'keys') else r[5],
            })
        return jsonify({'ok': True, 'items': items, 'count': len(items)})
    finally:
        conn.close()


@media_curriculum_bp.route('/api/kc/media/curriculum', methods=['POST'])
def add_curriculum():
    data  = request.get_json(silent=True) or {}
    # Y.55: type-check before .strip() (Y.50 class).
    for col in ('topic', 'kind', 'tool', 'notes'):
        v = data.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({'ok': False, 'error': f'{col} must be a string'}), 400
    topic = (data.get('topic') or '').strip()[:120]
    kind  = (data.get('kind')  or '').strip().lower()
    tool  = (data.get('tool')  or '').strip()[:120]
    notes = (data.get('notes') or '').strip()[:500]
    if not topic or not tool:
        return jsonify({'ok': False, 'error': 'topic and tool are required'}), 400
    if kind not in _VALID_KINDS:
        return jsonify({'ok': False, 'error': f'invalid kind: {kind}'}), 400
    conn = get_connection()
    try:
        _ensure_schema(conn)
        try:
            conn.execute(
                "INSERT INTO kc_media_curriculum (topic, kind, tool, notes, created_at) "
                "VALUES (?,?,?,?,?)",
                (topic, kind, tool, notes, time.time()),
            )
            conn.commit()
            return jsonify({'ok': True, 'merged': False})
        except sqlite3.IntegrityError:
            # Unique conflict on (topic, kind, tool) → update notes only.
            conn.execute(
                "UPDATE kc_media_curriculum SET notes=? WHERE topic=? AND kind=? AND tool=?",
                (notes, topic, kind, tool),
            )
            conn.commit()
            return jsonify({'ok': True, 'merged': True})
    finally:
        conn.close()


@media_curriculum_bp.route('/api/kc/media/curriculum/<int:row_id>', methods=['DELETE'])
def delete_curriculum(row_id: int):
    conn = get_connection()
    try:
        _ensure_schema(conn)
        cur = conn.execute("DELETE FROM kc_media_curriculum WHERE id=?", (row_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
        return jsonify({'ok': True, 'deleted': cur.rowcount})
    finally:
        conn.close()


@media_curriculum_bp.route('/api/kc/media/trace', methods=['POST'])
def add_trace():
    data = request.get_json(silent=True) or {}
    # Y.55: type-check before .strip().
    for col in ('asset_id', 'project_id', 'agent'):
        v = data.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({'ok': False, 'error': f'{col} must be a string'}), 400
    asset_id   = (data.get('asset_id') or '').strip()[:120]
    project_id = (data.get('project_id') or '').strip()[:120] or None
    topics     = data.get('topics') or []
    tools      = data.get('tools')  or []
    agent      = (data.get('agent') or '').strip()[:60] or None
    if not asset_id:
        return jsonify({'ok': False, 'error': 'asset_id required'}), 400
    if not isinstance(topics, list) or not isinstance(tools, list):
        return jsonify({'ok': False, 'error': 'topics and tools must be arrays'}), 400
    topics = [str(t)[:120] for t in topics][:64]
    tools  = [str(t)[:120] for t in tools][:32]
    trace_id = f'TRACE-{uuid.uuid4().hex[:12].upper()}'
    conn = get_connection()
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO kc_media_trace (trace_id, asset_id, project_id, topics_json, tools_json, agent, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (trace_id, asset_id, project_id, json.dumps(topics), json.dumps(tools), agent, time.time()),
        )
        conn.commit()
        return jsonify({'ok': True, 'trace_id': trace_id})
    finally:
        conn.close()


@media_curriculum_bp.route('/api/kc/media/trace', methods=['GET'])
def list_trace():
    asset_id = (request.args.get('asset_id') or '').strip() or None
    conn = get_connection()
    try:
        _ensure_schema(conn)
        if asset_id:
            rows = conn.execute(
                "SELECT trace_id, asset_id, project_id, topics_json, tools_json, agent, created_at "
                "FROM kc_media_trace WHERE asset_id=? ORDER BY created_at DESC LIMIT 100",
                (asset_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT trace_id, asset_id, project_id, topics_json, tools_json, agent, created_at "
                "FROM kc_media_trace ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        items = []
        for r in rows:
            try:
                topics = json.loads(r['topics_json'] if hasattr(r, 'keys') else r[3])
            except Exception:
                topics = []
            try:
                tools = json.loads(r['tools_json'] if hasattr(r, 'keys') else r[4])
            except Exception:
                tools = []
            items.append({
                'trace_id':   r['trace_id']   if hasattr(r, 'keys') else r[0],
                'asset_id':   r['asset_id']   if hasattr(r, 'keys') else r[1],
                'project_id': r['project_id'] if hasattr(r, 'keys') else r[2],
                'topics':     topics,
                'tools':      tools,
                'agent':      r['agent']      if hasattr(r, 'keys') else r[5],
                'created_at': r['created_at'] if hasattr(r, 'keys') else r[6],
            })
        return jsonify({'ok': True, 'items': items, 'count': len(items)})
    finally:
        conn.close()
