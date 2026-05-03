"""Cyber Security pillar (Diamond layer).

Captures intrusion / hardening / audit events for the Swarm. Read by Seven
when asked about security posture; written by manual audits, killswitch
drills, and dependency-scan runs.

Table: cyber_audit_events
    event_id    TEXT PK
    ts          REAL    (epoch)
    severity    TEXT    info|low|medium|high|critical
    source      TEXT    free-form (e.g. 'killswitch', 'pip-audit', 'manual')
    summary     TEXT    one-line headline
    detail      TEXT    long-form (optional)
    status      TEXT    open|investigating|resolved|wont-fix
    created_at  REAL
    updated_at  REAL

Endpoints:
    GET    /api/cyber/events             list (newest first, ?limit=, ?status=)
    POST   /api/cyber/events             create
    PATCH  /api/cyber/events/<event_id>  update status / detail / summary
    DELETE /api/cyber/events/<event_id>  hard delete
    GET    /api/cyber/summary            counts by severity + open count
"""
from __future__ import annotations

import sqlite3
from typing import Any

from flask import Blueprint, jsonify, request

try:
    from blueprints._pillar_store import connect, ensure_columns, gen_id, now_ts
except ImportError:  # pragma: no cover - runtime path under frontend/
    from ._pillar_store import connect, ensure_columns, gen_id, now_ts

cybersecurity_bp = Blueprint('cybersecurity_bp', __name__)

PILLAR_SLUG = 'cyber-security'
TABLE = 'cyber_audit_events'
SEVERITIES = ('info', 'low', 'medium', 'high', 'critical')
OPEN_STATUSES = ('open', 'investigating')
ALL_STATUSES = ('open', 'investigating', 'resolved', 'wont-fix')


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            event_id    TEXT PRIMARY KEY,
            ts          REAL NOT NULL,
            severity    TEXT NOT NULL DEFAULT 'info',
            source      TEXT NOT NULL DEFAULT 'manual',
            summary     TEXT NOT NULL,
            detail      TEXT,
            status      TEXT NOT NULL DEFAULT 'open',
            created_at  REAL NOT NULL,
            updated_at  REAL
        )
        """
    )
    ensure_columns(conn, TABLE, {'detail': 'TEXT', 'updated_at': 'REAL'})
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def summary_for_seven() -> dict[str, Any]:
    """Tight snapshot for Seven's context block."""
    try:
        with connect() as conn:
            _init(conn)
            counts = {s: 0 for s in SEVERITIES}
            for r in conn.execute(
                f"SELECT severity, COUNT(*) AS n FROM {TABLE} "
                f"WHERE status IN ('open','investigating') GROUP BY severity"
            ):
                counts[r['severity']] = r['n']
            open_total = sum(counts.values())
            latest = conn.execute(
                f"SELECT event_id, severity, summary, ts FROM {TABLE} "
                f"WHERE status IN ('open','investigating') ORDER BY ts DESC LIMIT 3"
            ).fetchall()
    except sqlite3.Error:
        return {'pillar': PILLAR_SLUG, 'ok': False, 'open': 0, 'by_severity': {}, 'latest': []}
    return {
        'pillar': PILLAR_SLUG,
        'ok': True,
        'open': open_total,
        'by_severity': counts,
        'latest': [_row_to_dict(r) for r in latest],
    }


@cybersecurity_bp.route('/api/cyber/events', methods=['GET'])
def list_events():
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 500))
    except (TypeError, ValueError):
        limit = 50
    status = request.args.get('status')
    sql = f"SELECT * FROM {TABLE}"
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        _init(conn)
        rows = conn.execute(sql, params).fetchall()
    return jsonify({'ok': True, 'count': len(rows), 'events': [_row_to_dict(r) for r in rows]})


@cybersecurity_bp.route('/api/cyber/events', methods=['POST'])
def create_event():
    body = request.get_json(silent=True) or {}
    # Y.55: type-check before .strip()/.lower() (Y.50 class).
    for col in ('summary', 'severity', 'source', 'detail'):
        v = body.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({'ok': False, 'error': f'{col} must be a string'}), 400
    summary = (body.get('summary') or '').strip()
    if not summary:
        return jsonify({'ok': False, 'error': 'summary required'}), 400
    severity = (body.get('severity') or 'info').lower()
    if severity not in SEVERITIES:
        return jsonify({'ok': False, 'error': f'severity must be one of {SEVERITIES}'}), 400
    source = (body.get('source') or 'manual').strip() or 'manual'
    detail = body.get('detail')
    event_id = gen_id('CYB')
    ts = now_ts()
    with connect() as conn:
        _init(conn)
        conn.execute(
            f"INSERT INTO {TABLE} (event_id, ts, severity, source, summary, detail, "
            f"status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)",
            (event_id, ts, severity, source, summary, detail, ts, ts),
        )
        conn.commit()
    return jsonify({'ok': True, 'event_id': event_id}), 201


@cybersecurity_bp.route('/api/cyber/events/<event_id>', methods=['PATCH'])
def update_event(event_id: str):
    body = request.get_json(silent=True) or {}
    fields: dict[str, Any] = {}
    if 'status' in body:
        if body['status'] not in ALL_STATUSES:
            return jsonify({'ok': False, 'error': f'status must be one of {ALL_STATUSES}'}), 400
        fields['status'] = body['status']
    if 'severity' in body:
        if body['severity'] not in SEVERITIES:
            return jsonify({'ok': False, 'error': f'severity must be one of {SEVERITIES}'}), 400
        fields['severity'] = body['severity']
    for key in ('summary', 'detail', 'source'):
        if key in body:
            fields[key] = body[key]
    if not fields:
        return jsonify({'ok': False, 'error': 'no updatable fields'}), 400
    fields['updated_at'] = now_ts()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [event_id]
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"UPDATE {TABLE} SET {set_clause} WHERE event_id = ?", params)
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'event_id': event_id, 'updated': list(fields.keys())})


@cybersecurity_bp.route('/api/cyber/events/<event_id>', methods=['DELETE'])
def delete_event(event_id: str):
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"DELETE FROM {TABLE} WHERE event_id = ?", (event_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'event_id': event_id})


@cybersecurity_bp.route('/api/cyber/summary', methods=['GET'])
def get_summary():
    return jsonify(summary_for_seven())
