"""Financial Analytics pillar — investment-banking oriented.

NOT consumer finance. Captures positions / theses / deal-flow notes the
way a small IB desk would: ticker or deal codename, asset class, thesis,
notional + currency, status. Seven uses the summary to answer "what's on
the desk?" and "any high-conviction longs?".

Table: financial_positions
    position_id  TEXT PK
    ts           REAL
    ticker       TEXT      ticker / deal codename
    asset_class  TEXT      equity|fixed-income|fx|derivative|m&a|other
    thesis       TEXT
    notional     REAL      signed: positive = long, negative = short
    currency     TEXT      ISO-4217 (USD/EUR/GBP/AUD/ZAR/...)
    conviction   TEXT      low|medium|high
    status       TEXT      idea|opened|closed|cancelled
    created_at   REAL
    updated_at   REAL

Endpoints:
    GET    /api/financial/positions
    POST   /api/financial/positions
    PATCH  /api/financial/positions/<position_id>
    DELETE /api/financial/positions/<position_id>
    GET    /api/financial/summary
"""
from __future__ import annotations

import sqlite3
from typing import Any

from flask import Blueprint, jsonify, request

try:
    from blueprints._pillar_store import connect, ensure_columns, gen_id, now_ts
except ImportError:  # pragma: no cover
    from ._pillar_store import connect, ensure_columns, gen_id, now_ts

financial_bp = Blueprint('financial_bp', __name__)

PILLAR_SLUG = 'financial'
TABLE = 'financial_positions'
ASSET_CLASSES = ('equity', 'fixed-income', 'fx', 'derivative', 'm&a', 'other')
CONVICTIONS = ('low', 'medium', 'high')
ALL_STATUSES = ('idea', 'opened', 'closed', 'cancelled')
LIVE_STATUSES = ('idea', 'opened')


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            position_id  TEXT PRIMARY KEY,
            ts           REAL NOT NULL,
            ticker       TEXT NOT NULL,
            asset_class  TEXT NOT NULL DEFAULT 'equity',
            thesis       TEXT,
            notional     REAL NOT NULL DEFAULT 0,
            currency     TEXT NOT NULL DEFAULT 'USD',
            conviction   TEXT NOT NULL DEFAULT 'medium',
            status       TEXT NOT NULL DEFAULT 'idea',
            created_at   REAL NOT NULL,
            updated_at   REAL
        )
        """
    )
    ensure_columns(conn, TABLE, {'conviction': "TEXT NOT NULL DEFAULT 'medium'", 'updated_at': 'REAL'})
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def summary_for_seven() -> dict[str, Any]:
    try:
        with connect() as conn:
            _init(conn)
            placeholders = ','.join('?' for _ in LIVE_STATUSES)
            by_class: dict[str, dict[str, float]] = {}
            for r in conn.execute(
                f"SELECT asset_class, currency, "
                f"COUNT(*) AS n, COALESCE(SUM(notional), 0) AS gross "
                f"FROM {TABLE} WHERE status IN ({placeholders}) "
                f"GROUP BY asset_class, currency",
                LIVE_STATUSES,
            ):
                by_class.setdefault(r['asset_class'], {})[r['currency']] = {
                    'count': r['n'],
                    'gross_notional': r['gross'],
                }
            high = conn.execute(
                f"SELECT position_id, ticker, asset_class, notional, currency, conviction "
                f"FROM {TABLE} WHERE conviction = 'high' AND status IN ({placeholders}) "
                f"ORDER BY ts DESC LIMIT 5",
                LIVE_STATUSES,
            ).fetchall()
            total_open = conn.execute(
                f"SELECT COUNT(*) AS n FROM {TABLE} WHERE status IN ({placeholders})",
                LIVE_STATUSES,
            ).fetchone()['n']
    except sqlite3.Error:
        return {'pillar': PILLAR_SLUG, 'ok': False, 'open': 0, 'by_class': {}, 'high_conviction': []}
    return {
        'pillar': PILLAR_SLUG,
        'ok': True,
        'open': total_open,
        'by_class': by_class,
        'high_conviction': [_row_to_dict(r) for r in high],
    }


@financial_bp.route('/api/financial/positions', methods=['GET'])
def list_positions():
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
    return jsonify({'ok': True, 'count': len(rows), 'positions': [_row_to_dict(r) for r in rows]})


@financial_bp.route('/api/financial/positions', methods=['POST'])
def create_position():
    body = request.get_json(silent=True) or {}
    # Y.55: type-check before .strip()/.lower() (Y.50 class).
    for col in ('ticker', 'asset_class', 'conviction', 'currency', 'thesis'):
        v = body.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({'ok': False, 'error': f'{col} must be a string'}), 400
    ticker = (body.get('ticker') or '').strip()
    if not ticker:
        return jsonify({'ok': False, 'error': 'ticker required'}), 400
    asset_class = (body.get('asset_class') or 'equity').lower()
    if asset_class not in ASSET_CLASSES:
        return jsonify({'ok': False, 'error': f'asset_class must be one of {ASSET_CLASSES}'}), 400
    conviction = (body.get('conviction') or 'medium').lower()
    if conviction not in CONVICTIONS:
        return jsonify({'ok': False, 'error': f'conviction must be one of {CONVICTIONS}'}), 400
    try:
        notional = float(body.get('notional', 0))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'notional must be numeric'}), 400
    currency = (body.get('currency') or 'USD').upper()
    thesis = body.get('thesis')
    position_id = gen_id('FIN')
    ts = now_ts()
    with connect() as conn:
        _init(conn)
        conn.execute(
            f"INSERT INTO {TABLE} (position_id, ts, ticker, asset_class, thesis, notional, "
            f"currency, conviction, status, created_at, updated_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'idea', ?, ?)",
            (position_id, ts, ticker, asset_class, thesis, notional, currency, conviction, ts, ts),
        )
        conn.commit()
    return jsonify({'ok': True, 'position_id': position_id}), 201


@financial_bp.route('/api/financial/positions/<position_id>', methods=['PATCH'])
def update_position(position_id: str):
    body = request.get_json(silent=True) or {}
    fields: dict[str, Any] = {}
    if 'status' in body:
        if body['status'] not in ALL_STATUSES:
            return jsonify({'ok': False, 'error': f'status must be one of {ALL_STATUSES}'}), 400
        fields['status'] = body['status']
    if 'asset_class' in body:
        if body['asset_class'] not in ASSET_CLASSES:
            return jsonify({'ok': False, 'error': f'asset_class must be one of {ASSET_CLASSES}'}), 400
        fields['asset_class'] = body['asset_class']
    if 'conviction' in body:
        if body['conviction'] not in CONVICTIONS:
            return jsonify({'ok': False, 'error': f'conviction must be one of {CONVICTIONS}'}), 400
        fields['conviction'] = body['conviction']
    if 'notional' in body:
        try:
            fields['notional'] = float(body['notional'])
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'notional must be numeric'}), 400
    for key in ('ticker', 'thesis', 'currency'):
        if key in body:
            fields[key] = body[key]
    if not fields:
        return jsonify({'ok': False, 'error': 'no updatable fields'}), 400
    fields['updated_at'] = now_ts()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [position_id]
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"UPDATE {TABLE} SET {set_clause} WHERE position_id = ?", params)
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'position_id': position_id, 'updated': list(fields.keys())})


@financial_bp.route('/api/financial/positions/<position_id>', methods=['DELETE'])
def delete_position(position_id: str):
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"DELETE FROM {TABLE} WHERE position_id = ?", (position_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'position_id': position_id})


@financial_bp.route('/api/financial/summary', methods=['GET'])
def get_summary():
    return jsonify(summary_for_seven())
