"""Regression tests for backlog batch 9 (2026-05-02 session 28).

- S-859446F555: notification channel preferences
- S-BFCDBE9631: per-topic cadence override
- S-C75D565260: /api/tasker/history filters
- S-059100FE16: Fridays orchestrator scheduler awareness
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE notification_channel_prefs (
            key TEXT PRIMARY KEY,
            channels_json TEXT NOT NULL DEFAULT '["email"]',
            muted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE watched_topic_settings (
            topic_key TEXT PRIMARY KEY,
            digest_mode TEXT NOT NULL DEFAULT 'instant',
            digest_period_hours INTEGER NOT NULL DEFAULT 24,
            last_digest_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            cadence_minutes INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0,
            details_json TEXT DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()

    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    import importlib
    import utils.db._connection as conn_mod
    importlib.reload(conn_mod)
    monkeypatch.setattr(conn_mod, 'get_connection',
                        lambda: sqlite3.connect(str(db)))
    return str(db)


# S-859446F555 -------------------------------------------------------------

def test_get_channels_returns_default_when_no_row(fresh_db):
    from utils.notification_prefs import get_channels
    assert get_channels('topic:absent') == ['email']
    assert get_channels('topic:absent', default=['discord']) == ['discord']


def test_set_and_get_channels_round_trip(fresh_db):
    from utils.notification_prefs import set_channels, get_channels
    set_channels('topic:sap', ['email', 'discord'])
    assert get_channels('topic:sap') == ['email', 'discord']


def test_invalid_channel_is_dropped(fresh_db):
    from utils.notification_prefs import set_channels, get_channels
    set_channels('topic:x', ['email', 'pigeon', 'discord'])
    assert get_channels('topic:x') == ['email', 'discord']


def test_muted_returns_empty_channel_list(fresh_db):
    from utils.notification_prefs import set_channels, get_channels, is_muted
    set_channels('topic:quiet', ['email'], muted=True)
    assert get_channels('topic:quiet') == []
    assert is_muted('topic:quiet') is True


# S-BFCDBE9631 -------------------------------------------------------------

def test_cadence_minutes_column_exists(fresh_db):
    conn = sqlite3.connect(fresh_db)
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(watched_topic_settings)").fetchall()}
    conn.close()
    assert 'cadence_minutes' in cols


def test_cadence_minutes_persists(fresh_db):
    conn = sqlite3.connect(fresh_db)
    conn.execute(
        "INSERT INTO watched_topic_settings (topic_key, cadence_minutes) "
        "VALUES ('sap-news', 60)"
    )
    conn.commit()
    val = conn.execute(
        "SELECT cadence_minutes FROM watched_topic_settings "
        "WHERE topic_key='sap-news'"
    ).fetchone()[0]
    conn.close()
    assert val == 60


# S-C75D565260 -------------------------------------------------------------

def test_history_endpoint_filters_by_task_and_status(fresh_db, monkeypatch):
    conn = sqlite3.connect(fresh_db)
    conn.executemany(
        "INSERT INTO task_run_log (task_name, status, output, run_at) VALUES (?,?,?,?)",
        [
            ('alpha', 'ok',    'a-ok',  '2026-05-01 10:00:00'),
            ('alpha', 'error', 'a-err', '2026-05-01 11:00:00'),
            ('beta',  'ok',    'b-ok',  '2026-05-01 12:00:00'),
        ],
    )
    conn.commit()
    conn.close()

    from frontend.blueprints import tasker_bp as tb
    monkeypatch.setattr(tb, '_get_conn', lambda: sqlite3.connect(fresh_db))

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(tb.tasker_bp)
    client = app.test_client()

    r = client.get('/api/tasker/history?task=alpha')
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) == 2 and all(x['task_name'] == 'alpha' for x in rows)

    r = client.get('/api/tasker/history?status=error')
    rows = r.get_json()
    assert len(rows) == 1 and rows[0]['task_name'] == 'alpha'

    r = client.get('/api/tasker/history?since=2026-05-01 11:30:00')
    rows = r.get_json()
    assert len(rows) == 1 and rows[0]['task_name'] == 'beta'


# S-059100FE16 -------------------------------------------------------------

def test_orchestrator_skips_when_scheduler_recently_ran(fresh_db, monkeypatch):
    import importlib
    import fridays.orchestrator as orch
    # make heartbeat window short so the recent row qualifies
    monkeypatch.setattr(orch, 'HEARTBEAT_SECONDS', 600, raising=True)

    conn = sqlite3.connect(fresh_db)
    conn.execute(
        "INSERT INTO task_run_log (task_name, status, output, run_at) "
        "VALUES ('orchestrator_heartbeat', 'ok', 'sched ran', "
        "datetime('now', '-30 seconds'))"
    )
    conn.commit()
    conn.close()

    # database.get_connection used inside orchestrator
    import database as db_mod
    monkeypatch.setattr(db_mod, 'get_connection',
                        lambda: sqlite3.connect(fresh_db), raising=False)

    out = orch.run_heartbeat()
    assert out.get('skipped_reason') == 'scheduler_ran_recently'
    assert out.get('dispatched') == 0
