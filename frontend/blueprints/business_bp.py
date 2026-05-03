"""Business Centre pillar — accounting + payroll spine, everything else hangs off.

Lightweight ledger that captures any flow of value (income, expense,
payroll, transfer, accrual) so the user can stand up a real online
business on top later without throwing away history.

Table: business_ledger
    entry_id      TEXT PK
    ts            REAL
    kind          TEXT   income|expense|payroll|transfer|accrual
    amount        REAL   signed in original currency
    currency      TEXT   ISO-4217
    counterparty  TEXT   who/what
    category      TEXT   free-form bucket (e.g. 'cloud', 'salary', 'consulting')
    notes         TEXT
    status        TEXT   draft|posted|reconciled|void
    created_at    REAL
    updated_at    REAL

Endpoints:
    GET    /api/business/entries
    POST   /api/business/entries
    PATCH  /api/business/entries/<entry_id>
    DELETE /api/business/entries/<entry_id>
    GET    /api/business/summary
"""
from __future__ import annotations

import sqlite3
from typing import Any

from flask import Blueprint, jsonify, request

try:
    from blueprints._pillar_store import connect, ensure_columns, gen_id, now_ts
except ImportError:  # pragma: no cover
    from ._pillar_store import connect, ensure_columns, gen_id, now_ts

business_bp = Blueprint('business_bp', __name__)

PILLAR_SLUG = 'business'
TABLE = 'business_ledger'
KINDS = ('income', 'expense', 'payroll', 'transfer', 'accrual')
ALL_STATUSES = ('draft', 'posted', 'reconciled', 'void')
LIVE_STATUSES = ('posted', 'reconciled')


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            entry_id      TEXT PRIMARY KEY,
            ts            REAL NOT NULL,
            kind          TEXT NOT NULL DEFAULT 'expense',
            amount        REAL NOT NULL DEFAULT 0,
            currency      TEXT NOT NULL DEFAULT 'USD',
            counterparty  TEXT,
            category      TEXT,
            notes         TEXT,
            status        TEXT NOT NULL DEFAULT 'draft',
            created_at    REAL NOT NULL,
            updated_at    REAL
        )
        """
    )
    ensure_columns(conn, TABLE, {'category': 'TEXT', 'updated_at': 'REAL'})
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def summary_for_seven() -> dict[str, Any]:
    try:
        with connect() as conn:
            _init(conn)
            placeholders = ','.join('?' for _ in LIVE_STATUSES)
            net_by_ccy: dict[str, float] = {}
            for r in conn.execute(
                f"SELECT currency, COALESCE(SUM(amount), 0) AS net "
                f"FROM {TABLE} WHERE status IN ({placeholders}) GROUP BY currency",
                LIVE_STATUSES,
            ):
                net_by_ccy[r['currency']] = r['net']
            counts: dict[str, int] = {}
            for r in conn.execute(
                f"SELECT kind, COUNT(*) AS n FROM {TABLE} "
                f"WHERE status IN ({placeholders}) GROUP BY kind",
                LIVE_STATUSES,
            ):
                counts[r['kind']] = r['n']
            unreconciled = conn.execute(
                f"SELECT COUNT(*) AS n FROM {TABLE} WHERE status IN ('draft','posted')"
            ).fetchone()['n']
            recent = conn.execute(
                f"SELECT entry_id, ts, kind, amount, currency, counterparty, status "
                f"FROM {TABLE} ORDER BY ts DESC LIMIT 5"
            ).fetchall()
    except sqlite3.Error:
        return {
            'pillar': PILLAR_SLUG, 'ok': False, 'unreconciled': 0,
            'net_by_currency': {}, 'by_kind': {}, 'recent': [],
        }
    return {
        'pillar': PILLAR_SLUG,
        'ok': True,
        'unreconciled': unreconciled,
        'net_by_currency': net_by_ccy,
        'by_kind': counts,
        'recent': [_row_to_dict(r) for r in recent],
    }


@business_bp.route('/api/business/entries', methods=['GET'])
def list_entries():
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 500))
    except (TypeError, ValueError):
        limit = 50
    status = request.args.get('status')
    kind = request.args.get('kind')
    sql = f"SELECT * FROM {TABLE}"
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("status = ?")
        params.append(status)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        _init(conn)
        rows = conn.execute(sql, params).fetchall()
    return jsonify({'ok': True, 'count': len(rows), 'entries': [_row_to_dict(r) for r in rows]})


@business_bp.route('/api/business/entries', methods=['POST'])
def create_entry():
    body = request.get_json(silent=True) or {}
    # Y.55: type-check before .strip()/.lower() (Y.50 class).
    for col in ('kind', 'currency', 'counterparty', 'category', 'notes'):
        v = body.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({'ok': False, 'error': f'{col} must be a string'}), 400
    kind = (body.get('kind') or 'expense').lower()
    if kind not in KINDS:
        return jsonify({'ok': False, 'error': f'kind must be one of {KINDS}'}), 400
    try:
        amount = float(body.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'amount must be numeric'}), 400
    currency = (body.get('currency') or 'USD').upper()
    counterparty = body.get('counterparty')
    category = body.get('category')
    notes = body.get('notes')
    entry_id = gen_id('BUS')
    ts = now_ts()
    with connect() as conn:
        _init(conn)
        conn.execute(
            f"INSERT INTO {TABLE} (entry_id, ts, kind, amount, currency, counterparty, "
            f"category, notes, status, created_at, updated_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
            (entry_id, ts, kind, amount, currency, counterparty, category, notes, ts, ts),
        )
        conn.commit()
    return jsonify({'ok': True, 'entry_id': entry_id}), 201


@business_bp.route('/api/business/entries/<entry_id>', methods=['PATCH'])
def update_entry(entry_id: str):
    body = request.get_json(silent=True) or {}
    fields: dict[str, Any] = {}
    if 'status' in body:
        if body['status'] not in ALL_STATUSES:
            return jsonify({'ok': False, 'error': f'status must be one of {ALL_STATUSES}'}), 400
        fields['status'] = body['status']
    if 'kind' in body:
        if body['kind'] not in KINDS:
            return jsonify({'ok': False, 'error': f'kind must be one of {KINDS}'}), 400
        fields['kind'] = body['kind']
    if 'amount' in body:
        try:
            fields['amount'] = float(body['amount'])
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'amount must be numeric'}), 400
    for key in ('currency', 'counterparty', 'category', 'notes'):
        if key in body:
            fields[key] = body[key]
    if not fields:
        return jsonify({'ok': False, 'error': 'no updatable fields'}), 400
    fields['updated_at'] = now_ts()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [entry_id]
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"UPDATE {TABLE} SET {set_clause} WHERE entry_id = ?", params)
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'entry_id': entry_id, 'updated': list(fields.keys())})


@business_bp.route('/api/business/entries/<entry_id>', methods=['DELETE'])
def delete_entry(entry_id: str):
    with connect() as conn:
        _init(conn)
        cur = conn.execute(f"DELETE FROM {TABLE} WHERE entry_id = ?", (entry_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'entry_id': entry_id})


@business_bp.route('/api/business/summary', methods=['GET'])
def get_summary():
    return jsonify(summary_for_seven())


# Y.58 — IBank research-propositions stub. Captures intent to research a list
# of public propositions/acquisitions. Real implementation pulls from feeds.
@business_bp.route('/api/business/research-propositions', methods=['POST'])
def research_propositions():
    return jsonify({'ok': True, 'queued': True, 'note': 'IBank research request captured; awaiting markets-watch + feed wiring.'})
