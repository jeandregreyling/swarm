"""Regression tests for backlog batch 5 (2026-05-02 session 28).

- S-F8A20353D0: /api/tasker/health duplicate metric
- S-BFEE738F64: research_sessions.project_id link
- S-168F0F7D14: watcher_topic_last_seen table
- S-086BC371AD: email_retry_queue + send_reply enqueues on failure
"""
import contextlib
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE research_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            depth TEXT NOT NULL DEFAULT 'standard',
            status TEXT NOT NULL DEFAULT 'planning',
            phases_json TEXT NOT NULL DEFAULT '[]',
            linked_proposal_id TEXT DEFAULT '',
            requesting_agent TEXT NOT NULL DEFAULT 'user',
            summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            idempotency_key TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            project_id TEXT DEFAULT ''
        );
        CREATE UNIQUE INDEX idx_research_sessions_idem
            ON research_sessions(idempotency_key) WHERE idempotency_key != '';
        CREATE INDEX idx_research_sessions_project
            ON research_sessions(project_id) WHERE project_id != '';

        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            schedule TEXT DEFAULT '',
            action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1
        );
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE email_delivery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_address TEXT NOT NULL,
            cc TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            in_reply_to TEXT NOT NULL DEFAULT '',
            sent_at TEXT NOT NULL DEFAULT (datetime('now')),
            status TEXT NOT NULL DEFAULT 'ok',
            attempts INTEGER NOT NULL DEFAULT 1,
            error TEXT NOT NULL DEFAULT '',
            sender TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE email_retry_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_address TEXT NOT NULL,
            cc TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            html_body TEXT NOT NULL DEFAULT '',
            in_reply_to TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            attempts_remaining INTEGER NOT NULL DEFAULT 3,
            next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_error TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE watcher_topic_last_seen (
            topic_key TEXT PRIMARY KEY,
            last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_evidence_id INTEGER DEFAULT 0,
            evidence_count INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

    # Re-route both connection adapters used by the modules under test
    import importlib
    import utils.db._connection as conn_mod
    importlib.reload(conn_mod)
    monkeypatch.setattr(conn_mod, 'get_connection', lambda: sqlite3.connect(str(db)))

    return str(db)


# ---------------------------------------------------------------------------
# S-BFEE738F64
# ---------------------------------------------------------------------------

def test_research_session_links_to_project(isolated_db):
    from utils.db.research import create_session, get_session
    sid = create_session('topic-x', project_id='P-DEMO')
    row = get_session(sid)
    assert row['project_id'] == 'P-DEMO'


def test_research_session_default_project_id_is_empty(isolated_db):
    from utils.db.research import create_session, get_session
    sid = create_session('topic')
    assert get_session(sid)['project_id'] == ''


# ---------------------------------------------------------------------------
# S-168F0F7D14
# ---------------------------------------------------------------------------

def test_watcher_last_seen_table_exists(isolated_db):
    conn = sqlite3.connect(isolated_db)
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(watcher_topic_last_seen)").fetchall()}
    conn.close()
    assert {'topic_key', 'last_seen_at', 'last_evidence_id',
            'evidence_count', 'updated_at'}.issubset(cols)


def test_watcher_last_seen_upsert_works(isolated_db):
    """Demonstrate the table's intended usage pattern."""
    conn = sqlite3.connect(isolated_db)
    conn.execute(
        "INSERT INTO watcher_topic_last_seen (topic_key, last_evidence_id, evidence_count) "
        "VALUES ('sap-news', 42, 1)"
    )
    conn.execute(
        "INSERT INTO watcher_topic_last_seen (topic_key, last_evidence_id, evidence_count) "
        "VALUES ('sap-news', 99, 5) "
        "ON CONFLICT(topic_key) DO UPDATE SET "
        " last_evidence_id=excluded.last_evidence_id, "
        " evidence_count=excluded.evidence_count, "
        " updated_at=datetime('now')"
    )
    conn.commit()
    row = conn.execute(
        "SELECT last_evidence_id, evidence_count FROM watcher_topic_last_seen "
        "WHERE topic_key='sap-news'"
    ).fetchone()
    conn.close()
    assert row == (99, 5)


# ---------------------------------------------------------------------------
# S-086BC371AD
# ---------------------------------------------------------------------------

def test_send_reply_enqueues_on_failure(isolated_db):
    with patch('lib.email.email_handler.connect_smtp',
               side_effect=RuntimeError('smtp dead')):
        from lib.email.email_handler import send_reply
        ok = send_reply('alice@example.com', 'Hi', 'body',
                        original_message_id='<m1>', cc=['bob@example.com'])
    assert ok is False
    conn = sqlite3.connect(isolated_db)
    row = conn.execute(
        "SELECT to_address, cc, attempts, attempts_remaining, status, last_error "
        "FROM email_retry_queue ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 'alice@example.com'
    assert row[1] == 'bob@example.com'
    assert row[2] >= 1
    assert row[3] == 3
    assert row[4] == 'pending'
    assert 'smtp dead' in row[5]


def test_send_reply_does_not_enqueue_on_success(isolated_db):
    from unittest.mock import MagicMock
    with patch('lib.email.email_handler.connect_smtp') as mock_smtp:
        mock_smtp.return_value = MagicMock()
        from lib.email.email_handler import send_reply
        ok = send_reply('a@x.com', 'subj', 'body')
    assert ok is True
    conn = sqlite3.connect(isolated_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM email_retry_queue").fetchone()[0]
    conn.close()
    assert count == 0


# ---------------------------------------------------------------------------
# S-F8A20353D0  — Tasker health endpoint
# ---------------------------------------------------------------------------

def test_tasker_health_endpoint_reports_duplicates(isolated_db, monkeypatch):
    # Insert two scheduled_tasks rows with the same name to simulate duplicates.
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO scheduled_tasks (name, schedule, action_type, action_data) "
                 "VALUES ('dupe_task', '*/5 * * * *', 'python', 'foo')")
    conn.execute("INSERT INTO scheduled_tasks (name, schedule, action_type, action_data) "
                 "VALUES ('dupe_task', '0 * * * *', 'python', 'foo')")
    conn.execute("INSERT INTO scheduled_tasks (name, schedule, action_type, action_data) "
                 "VALUES ('unique_task', '*/5 * * * *', 'python', 'bar')")
    conn.commit()
    conn.close()

    # Wire blueprint's _get_conn to our test DB
    from frontend.blueprints import tasker_bp as tb
    monkeypatch.setattr(tb, '_get_conn', lambda: sqlite3.connect(isolated_db))

    # Build minimal Flask app + register blueprint
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(tb.tasker_bp)
    client = app.test_client()
    resp = client.get('/api/tasker/health')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['ok'] is True
    assert payload['total_tasks'] == 3
    assert payload['duplicate_count'] == 1
    names = [d['name'] for d in payload['duplicates']]
    assert 'dupe_task' in names
    assert payload['duplicates'][0]['count'] == 2
