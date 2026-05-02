"""Regression tests for backlog batch 8 (2026-05-02 session 28).

- S-6F23DD5914: research cancel/pause helpers
- S-8306533874: source quality scoring
- S-28178F1EF6: check_due lease-based concurrency
- S-E056DBAD19: service restart health warning
- S-B1279A66EB: listener code-version heartbeat
"""
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def hb_db(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE service_heartbeat (
            service_name TEXT PRIMARY KEY,
            code_version TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            last_beat_at TEXT NOT NULL DEFAULT '',
            pid INTEGER DEFAULT 0,
            restart_count INTEGER DEFAULT 0,
            last_restart_at TEXT NOT NULL DEFAULT ''
        );
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
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            schedule TEXT DEFAULT '',
            action_type TEXT DEFAULT 'PYTHON',
            action_data TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            next_run TEXT DEFAULT NULL,
            lease_owner TEXT DEFAULT '',
            lease_expires_at TEXT DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()

    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    import importlib
    import utils.db._connection as conn_mod
    importlib.reload(conn_mod)
    new_get = lambda: sqlite3.connect(str(db))
    monkeypatch.setattr(conn_mod, 'get_connection', new_get)
    # Other modules may have imported get_connection before this fixture
    # ran (e.g. via frontend.terminal.create_app() in another test).
    # Patch the bound names too so scheduler/database use our isolated DB.
    try:
        import database as _db
        monkeypatch.setattr(_db, 'get_connection', new_get, raising=False)
    except Exception:
        pass
    try:
        import fridays.scheduler as _sched
        monkeypatch.setattr(_sched, 'get_connection', new_get, raising=False)
    except Exception:
        pass
    return str(db)


# S-6F23DD5914 -------------------------------------------------------------

def test_cancel_session_sets_cancelled_status(hb_db):
    from utils.db.research import create_session, get_session, cancel_session
    sid = create_session('topic-z')
    cancel_session(sid, reason='operator stopped')
    s = get_session(sid)
    assert s['status'] == 'cancelled'
    assert 'operator stopped' in (s['last_error'] or '')


def test_pause_session_sets_paused_status(hb_db):
    from utils.db.research import create_session, get_session, pause_session, update_session
    sid = create_session('topic-y')
    pause_session(sid)
    assert get_session(sid)['status'] == 'paused'
    update_session(sid, status='searching')
    assert get_session(sid)['status'] == 'searching'


# S-8306533874 -------------------------------------------------------------

def test_score_source_quality_high_for_official_sap():
    from utils.db.research import score_source_quality
    s = score_source_quality(
        url='https://help.sap.com/docs/abap-platform/abap-rap',
        title='ABAP RAP overview',
        snippet='RESTful Application Programming model on the ABAP platform — '
                'official SAP documentation page describing key concepts.',
    )
    assert s >= 0.7


def test_score_source_quality_lower_for_thin_random():
    from utils.db.research import score_source_quality
    s = score_source_quality(url='https://random.example.org/post/1',
                             title='', snippet='short')
    assert s < 0.4


def test_score_source_quality_bumps_reputable_domains():
    from utils.db.research import score_source_quality
    s_repu = score_source_quality(
        url='https://stackoverflow.com/questions/123/how-to',
        title='How to do X',
        snippet='A long enough snippet describing the answer with multiple sentences here.',
    )
    s_unkn = score_source_quality(
        url='https://obscure-blog.example/post/123',
        title='How to do X',
        snippet='A long enough snippet describing the answer with multiple sentences here.',
    )
    assert s_repu > s_unkn


# S-28178F1EF6 -------------------------------------------------------------

def test_check_due_acquires_and_releases_lease(hb_db):
    from fridays import scheduler
    from fridays.task_runner import TASK_REGISTRY

    fired = []
    TASK_REGISTRY['_lease_probe'] = {
        'fn': lambda args='': (fired.append(1) or 'ok'),
        'description': 'p', 'category': 'test',
    }

    conn = sqlite3.connect(hb_db)
    conn.execute(
        "INSERT INTO scheduled_tasks (name, schedule, action_type, action_data, next_run) "
        "VALUES ('lease_probe', 'manual', 'PYTHON', '_lease_probe', NULL)"
    )
    conn.commit()
    conn.close()

    try:
        scheduler.check_due()
    finally:
        TASK_REGISTRY.pop('_lease_probe', None)

    assert fired == [1]
    conn = sqlite3.connect(hb_db)
    row = conn.execute(
        "SELECT lease_owner, lease_expires_at FROM scheduled_tasks "
        "WHERE name='lease_probe'"
    ).fetchone()
    conn.close()
    # lease must be released after the run
    assert (row[0] or '') == ''


# S-E056DBAD19 / S-B1279A66EB ---------------------------------------------

def test_record_startup_increments_restart_count(hb_db):
    from utils.service_heartbeat import record_startup
    record_startup('listener', code_version='abc1234')
    record_startup('listener', code_version='abc1234')
    record_startup('listener', code_version='abc1234')
    conn = sqlite3.connect(hb_db)
    row = conn.execute(
        "SELECT code_version, restart_count FROM service_heartbeat "
        "WHERE service_name='listener'"
    ).fetchone()
    conn.close()
    assert row[0] == 'abc1234'
    # First call inserts with 0; subsequent calls bump twice → count == 2
    assert row[1] == 2


def test_record_beat_updates_last_beat_at(hb_db):
    from utils.service_heartbeat import record_startup, record_beat
    record_startup('scheduler', code_version='v1')
    time.sleep(1.1)
    record_beat('scheduler')
    conn = sqlite3.connect(hb_db)
    row = conn.execute(
        "SELECT started_at, last_beat_at FROM service_heartbeat "
        "WHERE service_name='scheduler'"
    ).fetchone()
    conn.close()
    assert row[0] != row[1]


def test_warnings_flag_stale_heartbeat(hb_db):
    from utils.service_heartbeat import warnings as hb_warnings
    stale_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(hb_db)
    conn.execute(
        "INSERT INTO service_heartbeat (service_name, last_beat_at, started_at) "
        "VALUES ('crashed_svc', ?, ?)",
        (stale_time, stale_time),
    )
    conn.commit()
    conn.close()
    w = hb_warnings(stale_minutes=5, restart_threshold=99)
    assert any(item['service'] == 'crashed_svc' and item['kind'] == 'stale_heartbeat'
               for item in w)


def test_warnings_flag_frequent_restarts(hb_db):
    from utils.service_heartbeat import warnings as hb_warnings
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(hb_db)
    conn.execute(
        "INSERT INTO service_heartbeat (service_name, last_beat_at, started_at, "
        "restart_count, last_restart_at) VALUES ('flappy', ?, ?, 7, ?)",
        (now, now, now),
    )
    conn.commit()
    conn.close()
    w = hb_warnings(stale_minutes=999, restart_threshold=3)
    assert any(item['service'] == 'flappy' and item['kind'] == 'frequent_restarts'
               for item in w)
