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
PAPER_TABLE = 'trading_paper_trades'


def _init_paper(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {PAPER_TABLE} (
            trade_id      TEXT PRIMARY KEY,
            symbol        TEXT NOT NULL,
            side          TEXT NOT NULL,
            strategy      TEXT,
            entry_price   REAL NOT NULL,
            stop_loss     REAL NOT NULL,
            take_profit   REAL,
            quantity      REAL NOT NULL,
            risk_usd      REAL NOT NULL,
            exit_price    REAL,
            pnl           REAL,
            r_multiple    REAL,
            status        TEXT NOT NULL DEFAULT 'open',
            notes         TEXT,
            opened_at     REAL NOT NULL,
            closed_at     REAL
        )
        """
    )
    conn.commit()


def _paper_scorecard_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    from core.paper_trading_risk import DEFAULT_STARTING_CAPITAL, evaluate_portfolio_scorecard
    _init_paper(conn)
    closed = [_row_to_dict(r) for r in conn.execute(
        f"SELECT * FROM {PAPER_TABLE} WHERE status = 'closed' ORDER BY closed_at ASC"
    ).fetchall()]
    open_n = conn.execute(f"SELECT COUNT(*) AS n FROM {PAPER_TABLE} WHERE status = 'open'").fetchone()['n']
    card = evaluate_portfolio_scorecard(closed, starting_capital=DEFAULT_STARTING_CAPITAL)
    card['open_trades'] = open_n
    return card


@trading_bp.route('/api/trading/paper/size', methods=['POST'])
def paper_size():
    from core.paper_trading_risk import DEFAULT_RISK_PCT, size_position
    body = request.get_json(silent=True) or {}
    with connect() as conn:
        card = _paper_scorecard_from_db(conn)
    equity = float(body.get('equity') if body.get('equity') is not None else card['current_equity_usd'])
    try:
        sized = size_position(
            equity=equity,
            entry_price=float(body['entry_price']),
            stop_loss_price=float(body['stop_loss_price']),
            side=str(body.get('side') or 'buy'),
            risk_pct=float(body.get('risk_pct', DEFAULT_RISK_PCT)),
            take_profit_price=body.get('take_profit_price'),
        )
        return jsonify({'ok': True, 'sizing': sized})
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@trading_bp.route('/api/trading/paper/open', methods=['POST'])
def paper_open():
    from core.paper_trading_risk import DEFAULT_RISK_PCT, size_position
    body = request.get_json(silent=True) or {}
    symbol = str(body.get('symbol') or '').strip().upper()
    if not symbol:
        return jsonify({'ok': False, 'error': 'symbol is required'}), 400
    with connect() as conn:
        card = _paper_scorecard_from_db(conn)
        if card['circuit_breaker_tripped']:
            return jsonify({'ok': False, 'error': 'Paper circuit breaker tripped (>=15% drawdown); new trades halted'}), 409
        try:
            sized = size_position(
                equity=card['current_equity_usd'],
                entry_price=float(body['entry_price']),
                stop_loss_price=float(body['stop_loss_price']),
                side=str(body.get('side') or 'buy'),
                risk_pct=float(body.get('risk_pct', DEFAULT_RISK_PCT)),
                take_profit_price=body.get('take_profit_price'),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        trade_id = gen_id('PPR')
        ts = now_ts()
        conn.execute(
            f"INSERT INTO {PAPER_TABLE} (trade_id, symbol, side, strategy, entry_price, stop_loss, take_profit, "
            f"quantity, risk_usd, status, notes, opened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
            (
                trade_id, symbol, sized['side'], body.get('strategy') or '',
                sized['entry_price'], sized['stop_loss_price'], sized['take_profit_price'],
                sized['quantity'], sized['max_loss_usd'], body.get('notes') or '', ts,
            ),
        )
        conn.commit()
    return jsonify({'ok': True, 'paper_only': True, 'trade_id': trade_id, 'sizing': sized}), 201


@trading_bp.route('/api/trading/paper/<trade_id>/close', methods=['POST'])
def paper_close(trade_id: str):
    body = request.get_json(silent=True) or {}
    try:
        exit_price = float(body['exit_price'])
        if exit_price <= 0:
            raise ValueError('exit_price must be positive')
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    with connect() as conn:
        _init_paper(conn)
        row = conn.execute(f"SELECT * FROM {PAPER_TABLE} WHERE trade_id = ?", (trade_id,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'paper trade not found'}), 404
        if row['status'] != 'open':
            return jsonify({'ok': False, 'error': 'paper trade already closed'}), 409
        entry = float(row['entry_price'])
        qty = float(row['quantity'])
        risk_usd = float(row['risk_usd']) or 1.0
        pnl = round((exit_price - entry) * qty if row['side'] == 'buy' else (entry - exit_price) * qty, 2)
        r_mult = round(pnl / risk_usd, 2)
        conn.execute(
            f"UPDATE {PAPER_TABLE} SET exit_price = ?, pnl = ?, r_multiple = ?, status = 'closed', closed_at = ? WHERE trade_id = ?",
            (exit_price, pnl, r_mult, now_ts(), trade_id),
        )
        conn.commit()
        card = _paper_scorecard_from_db(conn)
    return jsonify({'ok': True, 'trade_id': trade_id, 'pnl': pnl, 'r_multiple': r_mult, 'scorecard': card})


@trading_bp.route('/api/trading/paper/scorecard', methods=['GET'])
def paper_scorecard():
    with connect() as conn:
        card = _paper_scorecard_from_db(conn)
        trades = [_row_to_dict(r) for r in conn.execute(
            f"SELECT * FROM {PAPER_TABLE} ORDER BY opened_at DESC LIMIT 50"
        ).fetchall()]
    return jsonify({'ok': True, 'scorecard': card, 'trades': trades})


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
