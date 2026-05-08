"""Online Trading pillar.

The user prefers the framing 'online trading' over 'crypto' — same code
path either way. Captures trade signals (idea, side, strategy, confidence)
and lets you flip them through the lifecycle: pending -> filled -> closed.

Table: trading_signals
    signal_id    TEXT PK
    ts           REAL
    symbol       TEXT      e.g. BTC-USD, AAPL, EUR/USD
    side         TEXT      buy|sell
    strategy     TEXT      free-form (e.g. 'breakout', 'mean-reversion')
    confidence   REAL      0.0..1.0
    notes        TEXT
    status       TEXT      pending|filled|closed|cancelled
    pnl          REAL      optional, nullable
    created_at   REAL
    updated_at   REAL

Endpoints:
    GET    /api/trading/signals
    POST   /api/trading/signals
    PATCH  /api/trading/signals/<signal_id>
    DELETE /api/trading/signals/<signal_id>
    GET    /api/trading/summary
"""
from __future__ import annotations

import sqlite3
from typing import Any

from flask import Blueprint, jsonify, request

try:
    from blueprints._pillar_store import connect, ensure_columns, gen_id, now_ts
except ImportError:  # pragma: no cover
    from ._pillar_store import connect, ensure_columns, gen_id, now_ts

trading_bp = Blueprint('trading_bp', __name__)

PILLAR_SLUG = 'trading'
TABLE = 'trading_signals'
SIDES = ('buy', 'sell')
ALL_STATUSES = ('pending', 'filled', 'closed', 'cancelled')
LIVE_STATUSES = ('pending', 'filled')


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            signal_id    TEXT PRIMARY KEY,
            ts           REAL NOT NULL,
            symbol       TEXT NOT NULL,
            side         TEXT NOT NULL,
            strategy     TEXT,
            confidence   REAL NOT NULL DEFAULT 0.5,
            notes        TEXT,
            status       TEXT NOT NULL DEFAULT 'pending',
            pnl          REAL,
            created_at   REAL NOT NULL,
            updated_at   REAL
        )
        """
    )
    ensure_columns(conn, TABLE, {'pnl': 'REAL', 'updated_at': 'REAL'})
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def summary_for_seven() -> dict[str, Any]:
    try:
        with connect() as conn:
            _init(conn)
            placeholders = ','.join('?' for _ in LIVE_STATUSES)
            buy_n = conn.execute(
                f"SELECT COUNT(*) AS n FROM {TABLE} WHERE side = 'buy' AND status IN ({placeholders})",
                LIVE_STATUSES,
            ).fetchone()['n']
            sell_n = conn.execute(
                f"SELECT COUNT(*) AS n FROM {TABLE} WHERE side = 'sell' AND status IN ({placeholders})",
                LIVE_STATUSES,
            ).fetchone()['n']
            realised = conn.execute(
                f"SELECT COALESCE(SUM(pnl), 0) AS p FROM {TABLE} WHERE status = 'closed'"
            ).fetchone()['p']
            top = conn.execute(
                f"SELECT signal_id, symbol, side, strategy, confidence, status "
                f"FROM {TABLE} WHERE status IN ({placeholders}) "
                f"ORDER BY confidence DESC, ts DESC LIMIT 5",
                LIVE_STATUSES,
            ).fetchall()
    except sqlite3.Error:
        return {'pillar': PILLAR_SLUG, 'ok': False, 'open': 0, 'by_side': {}, 'realised_pnl': 0.0, 'top': []}
    return {
        'pillar': PILLAR_SLUG,
        'ok': True,
        'open': buy_n + sell_n,
        'by_side': {'buy': buy_n, 'sell': sell_n},
        'realised_pnl': realised,
        'top': [_row_to_dict(r) for r in top],
    }


def _validate_confidence(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= f <= 1.0:
        return None
    return f


@trading_bp.route('/api/trading/signals', methods=['GET'])
def list_signals():
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
    return jsonify({'ok': True, 'count': len(rows), 'signals': [_row_to_dict(r) for r in rows]})


@trading_bp.route('/api/trading/signals', methods=['POST'])
def create_signal():
    body = request.get_json(silent=True) or {}
    # Y.55: type-check before .strip()/.lower() (Y.50 class).
    for col in ('symbol', 'side', 'strategy', 'notes'):
        v = body.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({'ok': False, 'error': f'{col} must be a string'}), 400
    symbol = (body.get('symbol') or '').strip()
    if not symbol:
        return jsonify({'ok': False, 'error': 'symbol required'}), 400
    side = (body.get('side') or '').lower()
    if side not in SIDES:
        return jsonify({'ok': False, 'error': f'side must be one of {SIDES}'}), 400
    confidence = _validate_confidence(body.get('confidence', 0.5))
    if confidence is None:
        return jsonify({'ok': False, 'error': 'confidence must be 0.0..1.0'}), 400
    strategy = body.get('strategy')
    notes = body.get('notes')
    signal_id = gen_id('TRD')
    ts = now_ts()
    with connect() as conn:
        _init(conn)
        conn.execute(
            f"INSERT INTO {TABLE} (signal_id, ts, symbol, side, strategy, confidence, "
            f"notes, status, created_at, updated_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (signal_id, ts, symbol, side, strategy, confidence, notes, ts, ts),
        )
        conn.commit()
    return jsonify({'ok': True, 'signal_id': signal_id}), 201


@trading_bp.route('/api/trading/signals/<signal_id>', methods=['PATCH'])
def update_signal(signal_id: str):
    body = request.get_json(silent=True) or {}
    fields: dict[str, Any] = {}
    if 'status' in body:
        if body['status'] not in ALL_STATUSES:
            return jsonify({'ok': False, 'error': f'status must be one of {ALL_STATUSES}'}), 400
        fields['status'] = body['status']
    if 'side' in body:
        if body['side'] not in SIDES:
            return jsonify({'ok': False, 'error': f'side must be one of {SIDES}'}), 400
        fields['side'] = body['side']
    if 'confidence' in body:
        c = _validate_confidence(body['confidence'])
        if c is None:
            return jsonify({'ok': False, 'error': 'confidence must be 0.0..1.0'}), 400
        fields['confidence'] = c
    if 'pnl' in body:
        try:
            fields['pnl'] = float(body['pnl'])
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'pnl must be numeric'}), 400
    for key in ('symbol', 'strategy', 'notes'):
        if key in body:
            fields[key] = body[key]
    if not fields:
        return jsonify({'ok': False, 'error': 'no updatable fields'}), 400
    fields['updated_at'] = now_ts()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [signal_id]
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"UPDATE {TABLE} SET {set_clause} WHERE signal_id = ?", params)
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'signal_id': signal_id, 'updated': list(fields.keys())})


@trading_bp.route('/api/trading/signals/<signal_id>', methods=['DELETE'])
def delete_signal(signal_id: str):
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"DELETE FROM {TABLE} WHERE signal_id = ?", (signal_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'signal_id': signal_id})


@trading_bp.route('/api/trading/summary', methods=['GET'])
def get_summary():
    return jsonify(summary_for_seven())


# Y.58 — Pattern detection stub. Logs a request to scan known symbols for
# breakout / mean-reversion / divergence patterns. Real implementation will
# consume Tasker output once markets-watch job lands.
@trading_bp.route('/api/trading/scan-patterns', methods=['POST'])
def scan_patterns():
    from flask import request as _req  # local import to avoid module-load order issues
    payload = _req.get_json(silent=True) or {}
    symbols = payload.get('symbols') if isinstance(payload, dict) else None
    queued = 0
    try:
        with connect() as conn:
            _init(conn)
            cur = conn.execute(f"SELECT DISTINCT symbol FROM {TABLE} LIMIT 200")
            rows = [r[0] for r in cur.fetchall() if r and r[0]]
            queued = len(symbols) if isinstance(symbols, list) else len(rows)
    except sqlite3.Error:
        queued = 0
    return jsonify({'ok': True, 'queued': queued, 'note': 'pattern scan accepted; real scan runs via Tasker markets-watch.'})
