"""Regression tests for backlog batch 6 (2026-05-02 session 28).

- S-6E6CD8BA76: research evidence is_novel annotation
- S-4A136CB7F8: list_registered exposes function params
- S-DB17B92842: watched_topic_settings digest mode
- S-F98ABAB164: scheduled_tasks.missed_run_policy column
"""
import sqlite3
import sys
from pathlib import Path

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
            depth TEXT DEFAULT 'standard',
            status TEXT DEFAULT 'planning',
            phases_json TEXT DEFAULT '[]',
            linked_proposal_id TEXT DEFAULT '',
            requesting_agent TEXT DEFAULT 'user',
            summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            idempotency_key TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            project_id TEXT DEFAULT ''
        );
        CREATE TABLE research_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            source_url TEXT DEFAULT '',
            source_type TEXT DEFAULT 'web',
            title TEXT DEFAULT '',
            snippet TEXT DEFAULT '',
            confidence REAL DEFAULT 0.5,
            collecting_agent TEXT DEFAULT '',
            snippet_hash TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX idx_research_evidence_dedup
            ON research_evidence (session_id, source_url, snippet_hash);

        CREATE TABLE watched_topic_settings (
            topic_key TEXT PRIMARY KEY,
            digest_mode TEXT NOT NULL DEFAULT 'instant',
            digest_period_hours INTEGER NOT NULL DEFAULT 24,
            last_digest_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            schedule TEXT DEFAULT '',
            action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            missed_run_policy TEXT DEFAULT 'skip'
        );
    """)
    conn.commit()
    conn.close()

    import importlib
    import utils.db._connection as conn_mod
    importlib.reload(conn_mod)
    monkeypatch.setattr(conn_mod, 'get_connection', lambda: sqlite3.connect(str(db)))
    return str(db)


# S-6E6CD8BA76 -------------------------------------------------------------

def test_evidence_is_novel_first_seen(isolated_db):
    from utils.db.research import create_session, add_evidence, get_evidence_for_session
    sid = create_session('topic')
    add_evidence(sid, source_url='https://a.example/1',
                 snippet='unique payload one')
    rows = get_evidence_for_session(sid)
    assert len(rows) == 1
    assert rows[0]['is_novel'] is True


def test_evidence_is_not_novel_when_seen_in_earlier_session(isolated_db):
    from utils.db.research import create_session, add_evidence, get_evidence_for_session
    sid_old = create_session('first run')
    add_evidence(sid_old, source_url='https://a.example/1', snippet='same content')

    sid_new = create_session('second run')
    add_evidence(sid_new, source_url='https://b.example/1', snippet='same content')

    rows = get_evidence_for_session(sid_new)
    assert len(rows) == 1
    assert rows[0]['is_novel'] is False


# S-4A136CB7F8 -------------------------------------------------------------

def test_list_registered_includes_params():
    from fridays.task_runner import TASK_REGISTRY, list_registered

    def _probe(args='', flag=False):
        return 'ok'

    TASK_REGISTRY['__sig_probe'] = {
        'fn': _probe, 'description': 'sig test', 'category': 'probe',
    }
    try:
        out = list_registered()
        entry = next(e for e in out if e['name'] == '__sig_probe')
        assert entry['description'] == 'sig test'
        param_names = [p['name'] for p in entry['params']]
        assert 'args' in param_names
        assert 'flag' in param_names
        flag_param = next(p for p in entry['params'] if p['name'] == 'flag')
        assert flag_param['has_default'] is True
        assert flag_param['default'] == 'False'
    finally:
        TASK_REGISTRY.pop('__sig_probe', None)


# S-DB17B92842 -------------------------------------------------------------

def test_watched_topic_settings_default_digest_mode(isolated_db):
    conn = sqlite3.connect(isolated_db)
    conn.execute(
        "INSERT INTO watched_topic_settings (topic_key) VALUES ('sap-news')"
    )
    conn.commit()
    row = conn.execute(
        "SELECT digest_mode, digest_period_hours FROM watched_topic_settings "
        "WHERE topic_key='sap-news'"
    ).fetchone()
    conn.close()
    assert row == ('instant', 24)


def test_watched_topic_settings_can_be_set_to_digest(isolated_db):
    conn = sqlite3.connect(isolated_db)
    conn.execute(
        "INSERT INTO watched_topic_settings "
        "(topic_key, digest_mode, digest_period_hours) "
        "VALUES ('cyber', 'digest', 12)"
    )
    conn.commit()
    row = conn.execute(
        "SELECT digest_mode, digest_period_hours FROM watched_topic_settings "
        "WHERE topic_key='cyber'"
    ).fetchone()
    conn.close()
    assert row == ('digest', 12)


# S-F98ABAB164 -------------------------------------------------------------

def test_scheduled_tasks_has_missed_run_policy(isolated_db):
    conn = sqlite3.connect(isolated_db)
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(scheduled_tasks)").fetchall()}
    conn.close()
    assert 'missed_run_policy' in cols


def test_missed_run_policy_default_is_skip(isolated_db):
    conn = sqlite3.connect(isolated_db)
    conn.execute(
        "INSERT INTO scheduled_tasks (name, schedule, action_type, action_data) "
        "VALUES ('test_task', '*/5 * * * *', 'python', 'foo')"
    )
    conn.commit()
    row = conn.execute(
        "SELECT missed_run_policy FROM scheduled_tasks WHERE name='test_task'"
    ).fetchone()
    conn.close()
    assert row[0] == 'skip'
