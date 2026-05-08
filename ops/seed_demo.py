"""Seed a fresh swarm DB with a small, real-looking demo dataset across all
four wishlist pillars so a first-time user lands on a populated UI rather
than four empty tiles.

Idempotent: each row uses a deterministic id; running twice does not double.
Safe: only writes the four pillar tables. Never touches identity beliefs,
projects, or proposals.

Run:    python -m ops.seed_demo            # seeds via in-process imports
        python -m ops.seed_demo --reset    # clears then reseeds
"""

from __future__ import annotations

import os
import sys
import time
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / 'frontend'))

from blueprints._pillar_store import db_path, connect, ensure_columns  # noqa: E402

DEMO = {
    'cyber_audit_events': [
        ('CYB-DEMO0001', int(time.time()) - 3600, 'high', 'firewall', 'Outbound 4444 anomaly', 'Container egress to unknown IP', 'open'),
        ('CYB-DEMO0002', int(time.time()) - 7200, 'medium', 'ssh', 'Repeated auth failures', '12 failed root attempts in 60s', 'investigating'),
        ('CYB-DEMO0003', int(time.time()) - 86400, 'low', 'tls', 'Cert expiry < 30d', 'gateway.local valid until 2026-05-30', 'open'),
    ],
    'financial_positions': [
        ('FIN-DEMO0001', int(time.time()) - 86400, 'AAPL', 'equity', 'Long thesis on services revenue mix', 100000.0, 'USD', 'high', 'opened'),
        ('FIN-DEMO0002', int(time.time()) - 172800, 'EUR/USD', 'fx', 'ECB pause; mean revert 1.08', 25000.0, 'EUR', 'medium', 'idea'),
    ],
    'trading_signals': [
        ('TRD-DEMO0001', int(time.time()) - 1800, 'BTC-USD', 'buy', 'breakout', 0.72, 'Range top break + vol expansion', 'pending', 0.0),
        ('TRD-DEMO0002', int(time.time()) - 9000, 'ETH-USD', 'sell', 'mean-revert', 0.55, 'RSI extension fade', 'closed', 142.50),
    ],
    'business_ledger': [
        ('BUS-DEMO0001', int(time.time()) - 86400, 'expense', -49.99, 'USD', 'Anthropic', 'cloud', 'monthly Claude bill', 'posted'),
        ('BUS-DEMO0002', int(time.time()) - 172800, 'income', 1200.00, 'USD', 'Client Acme', 'consulting', 'May retainer', 'reconciled'),
    ],
}


def _ensure_schema(conn):
    # Mirror the pillar blueprints' CREATE TABLE statements minimally so seeding
    # works even if no blueprint has been imported yet in this process.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cyber_audit_events (
        event_id TEXT PRIMARY KEY, ts INTEGER, severity TEXT, source TEXT,
        summary TEXT, detail TEXT, status TEXT, created_at INTEGER, updated_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS financial_positions (
        position_id TEXT PRIMARY KEY, ts INTEGER, ticker TEXT, asset_class TEXT,
        thesis TEXT, notional REAL, currency TEXT, conviction TEXT, status TEXT,
        created_at INTEGER, updated_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS trading_signals (
        signal_id TEXT PRIMARY KEY, ts INTEGER, symbol TEXT, side TEXT,
        strategy TEXT, confidence REAL, notes TEXT, status TEXT, pnl REAL,
        created_at INTEGER, updated_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS business_ledger (
        entry_id TEXT PRIMARY KEY, ts INTEGER, kind TEXT, amount REAL,
        currency TEXT, counterparty TEXT, category TEXT, notes TEXT,
        status TEXT, created_at INTEGER, updated_at INTEGER
    );
    """)


def seed(reset: bool = False) -> dict:
    conn = connect()
    try:
        _ensure_schema(conn)
        if reset:
            for t in DEMO:
                conn.execute(f"DELETE FROM {t} WHERE rowid IN (SELECT rowid FROM {t} WHERE "
                             f"{('event_id' if t == 'cyber_audit_events' else 'position_id' if t=='financial_positions' else 'signal_id' if t=='trading_signals' else 'entry_id')} LIKE '%-DEMO%')")
        out = {}
        now = int(time.time())

        for row in DEMO['cyber_audit_events']:
            conn.execute("INSERT OR IGNORE INTO cyber_audit_events VALUES (?,?,?,?,?,?,?,?,?)",
                         row + (now, now))
        for row in DEMO['financial_positions']:
            conn.execute("INSERT OR IGNORE INTO financial_positions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         row + (now, now))
        for row in DEMO['trading_signals']:
            conn.execute("INSERT OR IGNORE INTO trading_signals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         row + (now, now))
        for row in DEMO['business_ledger']:
            conn.execute("INSERT OR IGNORE INTO business_ledger VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         row + (now, now))
        conn.commit()

        for t in DEMO:
            out[t] = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()[0]
        return {'ok': True, 'db': str(db_path()), 'counts': out}
    finally:
        conn.close()


if __name__ == '__main__':
    reset = '--reset' in sys.argv[1:]
    res = seed(reset=reset)
    print(res)
