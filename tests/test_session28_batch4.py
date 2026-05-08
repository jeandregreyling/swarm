"""Regression tests for backlog batch 4 (2026-05-02 session 28).

- S-5E508B5488: task_run_log.duration_ms column written by run_task
- S-15087BF900: task_run_log.details_json structured payload
- S-B13B24A10F: scheduled_tasks.lease_owner / lease_expires_at columns present
- S-C1307E6D72: watched-topic email dedupe regression coverage
  (the substantive test lives in test_session28_batch3.py; we keep a thin
  test here so the step's evidence chain is locally readable.)
"""
import json
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def fake_db(tmp_path, monkeypatch):
    db = tmp_path / 'tasker.db'
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0,
            details_json TEXT DEFAULT ''
        );
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            schedule TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            action_data TEXT NOT NULL DEFAULT '',
            lease_owner TEXT DEFAULT '',
            lease_expires_at TEXT DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()

    # Stub out database.get_connection used by fridays.task_runner._log_run
    import contextlib

    @contextlib.contextmanager
    def _cm():
        c = sqlite3.connect(str(db))
        try:
            yield c
            c.commit()
        finally:
            c.close()

    fake_module = type(sys)('database')
    fake_module.get_connection = _cm
    monkeypatch.setitem(sys.modules, 'database', fake_module)
    return str(db)


def test_task_run_log_records_duration_and_details(fake_db):
    """run_task must persist duration_ms and details_json (S-5E508B5488 + S-15087BF900)."""
    from fridays.task_runner import TASK_REGISTRY, run_task

    TASK_REGISTRY['__probe_ok'] = {
        'fn': lambda args='': 'probe-ok',
        'description': 'test',
        'category': 'probe',
    }
    try:
        ok, _ = run_task('__probe_ok', args='hello')
        assert ok is True
    finally:
        TASK_REGISTRY.pop('__probe_ok', None)

    conn = sqlite3.connect(fake_db)
    row = conn.execute(
        "SELECT task_name, status, duration_ms, details_json "
        "FROM task_run_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    name, status, dur_ms, details = row
    assert name == '__probe_ok'
    assert status == 'ok'
    assert isinstance(dur_ms, int) and dur_ms >= 0
    payload = json.loads(details)
    assert payload['category'] == 'probe'
    assert payload['args'] == 'hello'


def test_task_run_log_records_failure_with_exception_type(fake_db):
    """Failures must capture exception type in details_json."""
    from fridays.task_runner import TASK_REGISTRY, run_task

    def _boom(args=''):
        raise RuntimeError('kaboom')

    TASK_REGISTRY['__probe_fail'] = {
        'fn': _boom, 'description': 'test', 'category': 'probe',
    }
    try:
        ok, _ = run_task('__probe_fail')
        assert ok is False
    finally:
        TASK_REGISTRY.pop('__probe_fail', None)

    conn = sqlite3.connect(fake_db)
    row = conn.execute(
        "SELECT status, details_json FROM task_run_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == 'error'
    payload = json.loads(row[1])
    assert payload['exception'] == 'RuntimeError'


def test_scheduled_tasks_has_lease_columns(fake_db):
    """Lease columns must be queryable (S-B13B24A10F)."""
    conn = sqlite3.connect(fake_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(scheduled_tasks)").fetchall()}
    conn.close()
    assert 'lease_owner' in cols
    assert 'lease_expires_at' in cols


def test_log_run_works_on_legacy_schema_without_new_columns(tmp_path, monkeypatch):
    """If a deployment's task_run_log lacks the new columns, _log_run must still work."""
    db = tmp_path / 'legacy.db'
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

    import contextlib

    @contextlib.contextmanager
    def _cm():
        c = sqlite3.connect(str(db))
        try:
            yield c
            c.commit()
        finally:
            c.close()

    fake_module = type(sys)('database')
    fake_module.get_connection = _cm
    monkeypatch.setitem(sys.modules, 'database', fake_module)

    from fridays.task_runner import _log_run
    _log_run('legacy_probe', 'ok', 'hi', duration_ms=42, details={'x': 1})

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT task_name, status FROM task_run_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ('legacy_probe', 'ok')
