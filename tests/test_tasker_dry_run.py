"""S-A4249B4159 — `/api/tasker/tasks/<id>/dry-run` resolves a task without
executing it. Lets the user inspect handler binding + parsed args + projected
next_run before firing for real.

Companion regression for S-1C55C2826A (UNIQUE index on scheduled_tasks.name)
also lives here so the two changes co-evolve.
"""

import os
import sys
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            schedule TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_data TEXT NOT NULL,
            last_run TEXT,
            next_run TEXT,
            enabled INTEGER DEFAULT 1,
            created_by TEXT DEFAULT 'ghost',
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX idx_scheduled_tasks_name_unique
        ON scheduled_tasks(name) WHERE name IS NOT NULL AND name != ''
    """)
    conn.execute("""
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO scheduled_tasks(name,schedule,action_type,action_data,enabled) VALUES (?,?,?,?,1)",
        [
            ('demo_python', 'daily 06:30', 'PYTHON', 'demo_handler arg1 arg2'),
            ('demo_shell',  'interval 1h', 'SHELL',  '/bin/echo hello world'),
            ('demo_unreg',  'daily 07:30', 'PYTHON', 'never_registered_task'),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))

    import frontend.blueprints.tasker_bp as tb
    monkeypatch.setattr(tb, '_get_conn', lambda: sqlite3.connect(str(db)))
    monkeypatch.setattr(
        'fridays.task_runner.list_registered',
        lambda: [
            {'name': 'demo_handler', 'description': 'demo', 'callable': 'demo'},
        ],
    )

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(tb.tasker_bp)
    return app.test_client()


def test_dry_run_python_task_resolves_handler(app_client):
    r = app_client.post('/api/tasker/tasks/1/dry-run')
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True
    assert body['dry_run'] is True
    res = body['resolved']
    assert res['name'] == 'demo_python'
    assert res['action_type'] == 'PYTHON'
    assert res['enabled'] is True
    assert res['handler']['name'] == 'demo_handler'
    assert res['handler']['registered'] is True
    assert res['handler']['parsed_args'] == ['arg1', 'arg2']
    assert res['would_execute'] is True
    assert 'projected_next_run' in res


def test_dry_run_shell_task_parses_argv(app_client):
    r = app_client.post('/api/tasker/tasks/2/dry-run')
    body = r.get_json()
    assert body['ok'] is True
    res = body['resolved']
    assert res['action_type'] == 'SHELL'
    assert res['handler']['argv'] == ['/bin/echo', 'hello', 'world']
    assert res['handler']['binary'] == '/bin/echo'
    assert res['would_execute'] is True


def test_dry_run_unregistered_python_task_warns(app_client):
    r = app_client.post('/api/tasker/tasks/3/dry-run')
    body = r.get_json()
    assert body['ok'] is True
    res = body['resolved']
    assert res['handler']['registered'] is False
    assert res['would_execute'] is False
    assert 'not registered' in res['warning'].lower()


def test_dry_run_404_on_unknown_id(app_client):
    r = app_client.post('/api/tasker/tasks/9999/dry-run')
    assert r.status_code == 404
    assert r.get_json()['ok'] is False


def test_dry_run_does_not_mutate_row(app_client):
    """Critical contract: dry-run must NOT touch last_run / next_run."""
    db = os.environ['SWARM_MEMORY_DB']
    before = sqlite3.connect(db).execute(
        'SELECT last_run, next_run FROM scheduled_tasks WHERE id=1'
    ).fetchone()
    app_client.post('/api/tasker/tasks/1/dry-run')
    after = sqlite3.connect(db).execute(
        'SELECT last_run, next_run FROM scheduled_tasks WHERE id=1'
    ).fetchone()
    assert before == after


def test_scheduled_task_name_unique_constraint(app_client):
    """S-1C55C2826A — duplicate names must be rejected at the DB layer."""
    db = os.environ['SWARM_MEMORY_DB']
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO scheduled_tasks(name,schedule,action_type,action_data) "
            "VALUES('demo_python','daily 09:00','PYTHON','x')"
        )
    conn.close()
