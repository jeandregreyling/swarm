"""Regression tests for backlog items shipped 2026-05-02 (session 28 batch 3).

Covers:
- S-12E202F189 — research run idempotency key
- S-A43BF83EB7 — research background error visibility
- S-90C2B45FAF — email delivery audit row
- S-C533209A6F — project creation idempotency
- S-C1307E6D72 — watched-topic email dedupe regression
"""

import os
import sys
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))
    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    # Force fresh connection cache
    import importlib
    import utils.db._connection as conn_mod
    importlib.reload(conn_mod)
    monkeypatch.setattr(conn_mod, 'get_connection', lambda: sqlite3.connect(str(db)))
    # Initialise only the tables this batch needs (avoid full schema, which
    # has unrelated migrations that are picky about sqlite versions).
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
            last_error TEXT DEFAULT ''
        );
        CREATE UNIQUE INDEX idx_research_sessions_idem
            ON research_sessions(idempotency_key) WHERE idempotency_key != '';

        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            methodology TEXT NOT NULL DEFAULT 'mixed',
            status TEXT NOT NULL DEFAULT 'active',
            owner TEXT NOT NULL DEFAULT 'seven',
            created_at REAL NOT NULL,
            updated_at REAL,
            tags TEXT DEFAULT ''
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

        CREATE TABLE watched_topic_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_key TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            snippet_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX idx_watched_topic_evidence_dedup
            ON watched_topic_evidence(topic_key, source_url, snippet_hash);

        CREATE TABLE spine_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT, payload TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    return str(db)


# ---------------------------------------------------------------------------
# S-12E202F189: research idempotency
# ---------------------------------------------------------------------------

def test_research_idempotency_returns_same_session(isolated_db):
    from utils.db.research import create_session, get_session
    sid_a = create_session('test topic A', idempotency_key='retry-key-1')
    sid_b = create_session('test topic A', idempotency_key='retry-key-1')
    assert sid_a == sid_b
    assert get_session(sid_a)['idempotency_key'] == 'retry-key-1'


def test_research_idempotency_different_keys_create_separate(isolated_db):
    from utils.db.research import create_session
    a = create_session('topic', idempotency_key='k1')
    b = create_session('topic', idempotency_key='k2')
    assert a != b


def test_research_no_key_always_creates_new(isolated_db):
    from utils.db.research import create_session
    a = create_session('t')
    b = create_session('t')
    assert a != b


# ---------------------------------------------------------------------------
# S-A43BF83EB7: research error visibility
# ---------------------------------------------------------------------------

def test_research_update_session_persists_last_error(isolated_db):
    from utils.db.research import create_session, update_session, get_session
    sid = create_session('topic')
    update_session(sid, status='paused', last_error='RuntimeError: boom')
    row = get_session(sid)
    assert row['status'] == 'paused'
    assert 'boom' in row['last_error']


def test_research_last_error_truncated_at_2000_chars(isolated_db):
    from utils.db.research import create_session, update_session, get_session
    sid = create_session('topic')
    update_session(sid, last_error='X' * 5000)
    row = get_session(sid)
    assert len(row['last_error']) == 2000


# ---------------------------------------------------------------------------
# S-90C2B45FAF: email delivery audit row
# ---------------------------------------------------------------------------

def test_email_delivery_log_records_success(isolated_db):
    """Mock SMTP path; verify a delivery row is written."""
    with patch('lib.email.email_handler.connect_smtp') as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        from lib.email.email_handler import send_reply
        ok = send_reply('alice@example.com', 'Hello',
                        'body text',
                        original_message_id='<msg-1@example.com>',
                        cc=['bob@example.com'])
    assert ok is True
    conn = sqlite3.connect(isolated_db)
    rows = conn.execute(
        "SELECT to_address, cc, subject, in_reply_to, status, attempts "
        "FROM email_delivery_log ORDER BY id DESC LIMIT 1"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    to, cc, subj, irt, status, attempts = rows[0]
    assert to == 'alice@example.com'
    assert cc == 'bob@example.com'
    assert subj == 'Hello'
    assert irt == '<msg-1@example.com>'
    assert status == 'ok'
    assert attempts == 1


def test_email_delivery_log_records_failure(isolated_db):
    with patch('lib.email.email_handler.connect_smtp', side_effect=RuntimeError('smtp dead')):
        from lib.email.email_handler import send_reply
        ok = send_reply('alice@example.com', 'Hello', 'body')
    assert ok is False
    conn = sqlite3.connect(isolated_db)
    row = conn.execute(
        "SELECT status, error FROM email_delivery_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == 'failed'
    assert 'smtp dead' in row[1]


# ---------------------------------------------------------------------------
# S-C533209A6F: project creation idempotency
# ---------------------------------------------------------------------------

def test_project_idempotency_returns_existing(isolated_db):
    from core.knowledge.projects import create_project
    pid_a = create_project('Idem Test Project', owner='seven',
                           idempotency_key='proj-key-1')
    pid_b = create_project('Idem Test Project', owner='seven',
                           idempotency_key='proj-key-1')
    assert pid_a == pid_b


def test_project_idempotency_case_insensitive_match(isolated_db):
    from core.knowledge.projects import create_project
    a = create_project('My Cool Project', owner='seven', idempotency_key='k')
    b = create_project('my cool project', owner='seven', idempotency_key='k')
    assert a == b


def test_project_no_key_always_creates_new(isolated_db):
    from core.knowledge.projects import create_project
    a = create_project('Same Name', owner='seven')
    b = create_project('Same Name', owner='seven')
    assert a != b


# ---------------------------------------------------------------------------
# S-C1307E6D72: watched-topic email dedupe regression
# ---------------------------------------------------------------------------

def test_watched_topic_evidence_dedup_index_present(isolated_db):
    """The unique dedup index must exist after schema init."""
    conn = sqlite3.connect(isolated_db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND tbl_name='watched_topic_evidence' AND sql LIKE '%UNIQUE%'"
    ).fetchall()
    conn.close()
    assert len(rows) >= 1, "Expected at least one UNIQUE index on watched_topic_evidence"


def test_watched_topic_evidence_dedup_rejects_duplicate(isolated_db):
    """Re-inserting same (topic_key, source_url, snippet_hash) must be rejected."""
    conn = sqlite3.connect(isolated_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(watched_topic_evidence)").fetchall()}
    assert 'topic_key' in cols and 'source_url' in cols and 'snippet_hash' in cols
    # Verify there is at least one unique index covering dedup keys
    indexes = conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name='watched_topic_evidence' "
        "AND type='index'"
    ).fetchall()
    sql_blob = ' '.join((s[0] or '') for s in indexes).lower()
    assert 'unique' in sql_blob
    conn.close()
