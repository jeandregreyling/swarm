"""Synth-board: node/patch-board music workspace persistence.

STEP-MEDIA-CENTER-SYNTH-BOARD-20260430.

Stores JSON node-graphs (nodes + connections + arrangement) so agents and
users can save/load synth-board projects, and surfaces a small registry
that Knowledge Center can index later. Execution of a board (rendering
to audio) is delegated to the existing media_jobs queue; this module
only holds the patch-board document.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from flask import Blueprint, jsonify, request

synth_board_bp = Blueprint('synth_board', __name__)

_DB_PATH = 'swarm_memory.db'
_VALID_NODE_KINDS = {
    'oscillator', 'sampler', 'lfo', 'filter', 'envelope', 'delay',
    'reverb', 'compressor', 'eq', 'gain', 'mixer', 'sequencer',
    'arpeggiator', 'midi-in', 'audio-out', 'macro',
}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _ensure_tables(c: sqlite3.Connection) -> None:
    c.execute(
        '''
        CREATE TABLE IF NOT EXISTS synth_board_projects (
            board_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner TEXT,
            graph_json TEXT NOT NULL,
            tempo REAL,
            key TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        '''
    )
    c.execute(
        '''
        CREATE TABLE IF NOT EXISTS synth_board_revisions (
            rev_id TEXT PRIMARY KEY,
            board_id TEXT NOT NULL,
            graph_json TEXT NOT NULL,
            agent TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (board_id) REFERENCES synth_board_projects(board_id)
        )
        '''
    )
    c.commit()


def _now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())


def _validate_graph(graph: Any) -> tuple[bool, str]:
    if not isinstance(graph, dict):
        return False, 'graph must be an object'
    nodes = graph.get('nodes')
    edges = graph.get('edges', [])
    if not isinstance(nodes, list):
        return False, 'graph.nodes must be a list'
    if not isinstance(edges, list):
        return False, 'graph.edges must be a list'
    if len(nodes) > 256:
        return False, 'too many nodes (max 256)'
    if len(edges) > 1024:
        return False, 'too many edges (max 1024)'
    seen_ids: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict):
            return False, 'each node must be an object'
        nid = n.get('id')
        kind = n.get('kind')
        if not isinstance(nid, str) or not nid:
            return False, 'node.id required'
        if nid in seen_ids:
            return False, f'duplicate node id {nid}'
        seen_ids.add(nid)
        if kind not in _VALID_NODE_KINDS:
            return False, f'unknown node kind {kind!r}'
    for e in edges:
        if not isinstance(e, dict):
            return False, 'each edge must be an object'
        if e.get('from') not in seen_ids or e.get('to') not in seen_ids:
            return False, 'edge endpoints must reference known node ids'
    return True, ''


@synth_board_bp.route('/api/media/synth-board/projects', methods=['POST'])
def create_board():
    body = request.get_json(silent=True) or {}
    # Y.53: type-check string fields before .strip() to avoid 500 on
    # non-string input (same class of bug as Y.50 fixed in app_center).
    for col in ('name', 'owner', 'key', 'notes'):
        v = body.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify(ok=False, error=f'{col} must be a string'), 400
    name = (body.get('name') or '').strip()
    if not name or len(name) > 128:
        return jsonify(ok=False, error='name required (≤128)'), 400
    tempo_raw = body.get('tempo')
    if tempo_raw is not None and not isinstance(tempo_raw, (int, float)):
        return jsonify(ok=False, error='tempo must be a number'), 400
    if isinstance(tempo_raw, (int, float)) and (tempo_raw < 0 or tempo_raw > 600):
        return jsonify(ok=False, error='tempo out of range (0–600)'), 400
    graph = body.get('graph') or {'nodes': [], 'edges': []}
    ok, why = _validate_graph(graph)
    if not ok:
        return jsonify(ok=False, error=why), 400
    board_id = f'SBRD-{uuid.uuid4().hex[:12].upper()}'
    now = _now()
    c = _conn()
    try:
        _ensure_tables(c)
        c.execute(
            '''INSERT INTO synth_board_projects
               (board_id, name, owner, graph_json, tempo, key, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (
                board_id,
                name,
                (body.get('owner') or '').strip() or None,
                json.dumps(graph),
                float(tempo_raw) if tempo_raw is not None else None,
                (body.get('key') or '').strip() or None,
                (body.get('notes') or '').strip() or None,
                now,
                now,
            ),
        )
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True, board_id=board_id, created_at=now), 201


@synth_board_bp.route('/api/media/synth-board/projects', methods=['GET'])
def list_boards():
    c = _conn()
    try:
        _ensure_tables(c)
        rows = c.execute(
            'SELECT board_id, name, owner, tempo, key, updated_at FROM synth_board_projects '
            'ORDER BY updated_at DESC LIMIT 200'
        ).fetchall()
    finally:
        c.close()
    return jsonify(ok=True, count=len(rows), boards=[dict(r) for r in rows])


@synth_board_bp.route('/api/media/synth-board/projects/<board_id>', methods=['GET'])
def get_board(board_id: str):
    c = _conn()
    try:
        _ensure_tables(c)
        row = c.execute(
            'SELECT * FROM synth_board_projects WHERE board_id=?', (board_id,)
        ).fetchone()
    finally:
        c.close()
    if not row:
        return jsonify(ok=False, error='not found'), 404
    out = dict(row)
    out['graph'] = json.loads(out.pop('graph_json'))
    return jsonify(ok=True, board=out)


@synth_board_bp.route('/api/media/synth-board/projects/<board_id>', methods=['PATCH'])
def update_board(board_id: str):
    body = request.get_json(silent=True) or {}
    c = _conn()
    try:
        _ensure_tables(c)
        row = c.execute(
            'SELECT graph_json FROM synth_board_projects WHERE board_id=?', (board_id,)
        ).fetchone()
        if not row:
            return jsonify(ok=False, error='not found'), 404
        if 'graph' in body:
            ok, why = _validate_graph(body['graph'])
            if not ok:
                return jsonify(ok=False, error=why), 400
            # Save previous revision for history.
            rev_id = f'SREV-{uuid.uuid4().hex[:12].upper()}'
            c.execute(
                '''INSERT INTO synth_board_revisions (rev_id, board_id, graph_json, agent, created_at)
                   VALUES (?,?,?,?,?)''',
                (rev_id, board_id, row['graph_json'], (body.get('agent') or '').strip() or None, _now()),
            )
            c.execute(
                'UPDATE synth_board_projects SET graph_json=?, updated_at=? WHERE board_id=?',
                (json.dumps(body['graph']), _now(), board_id),
            )
        for col in ('name', 'tempo', 'key', 'notes'):
            if col not in body:
                continue
            value = body[col]
            if col in ('name', 'key', 'notes'):
                if value is not None and not isinstance(value, str):
                    return jsonify(ok=False, error=f'{col} must be a string'), 400
                if col == 'name' and (value is None or not value.strip()):
                    return jsonify(ok=False, error='name cannot be empty'), 400
                if isinstance(value, str) and len(value) > 128:
                    return jsonify(ok=False, error=f'{col} too long (max 128)'), 400
            elif col == 'tempo':
                if value is not None and not isinstance(value, (int, float)):
                    return jsonify(ok=False, error='tempo must be a number'), 400
                if isinstance(value, (int, float)) and (value < 0 or value > 600):
                    return jsonify(ok=False, error='tempo out of range (0–600)'), 400
            c.execute(
                f'UPDATE synth_board_projects SET {col}=?, updated_at=? WHERE board_id=?',
                (value, _now(), board_id),
            )
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True, board_id=board_id)


@synth_board_bp.route('/api/media/synth-board/projects/<board_id>/revisions', methods=['GET'])
def list_revisions(board_id: str):
    c = _conn()
    try:
        _ensure_tables(c)
        rows = c.execute(
            'SELECT rev_id, agent, created_at FROM synth_board_revisions '
            'WHERE board_id=? ORDER BY created_at DESC LIMIT 50',
            (board_id,),
        ).fetchall()
    finally:
        c.close()
    return jsonify(ok=True, count=len(rows), revisions=[dict(r) for r in rows])
