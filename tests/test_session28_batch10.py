"""Regression tests for backlog batch 10 (2026-05-02 session 28).

- S-0474A4BE17: projects.priority field + list ordering
- S-1E491C8128: API contract tests for /api/tasker
- S-247F1ED2E4: API contract tests for /api/research
- S-1C7E3AC503: listener restart timeout runbook exists
"""
import importlib
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
    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    import utils.db._connection as conn_mod
    importlib.reload(conn_mod)
    return str(db)


# S-0474A4BE17 ------------------------------------------------------------

def test_projects_priority_column_added(fresh_db):
    from core.knowledge import projects as proj_mod
    importlib.reload(proj_mod)
    pid = proj_mod.create_project('priority demo', description='x')
    assert pid is not None

    conn = sqlite3.connect(fresh_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    conn.close()
    assert 'priority' in cols


def test_update_project_accepts_priority(fresh_db):
    from core.knowledge import projects as proj_mod
    importlib.reload(proj_mod)
    pid = proj_mod.create_project('p1')
    assert proj_mod.update_project(pid, priority=5) is True
    info = proj_mod.get_project(pid)
    assert info and info['project']['priority'] == 5


def test_update_project_rejects_bad_priority(fresh_db):
    from core.knowledge import projects as proj_mod
    importlib.reload(proj_mod)
    pid = proj_mod.create_project('p2')
    with pytest.raises(ValueError):
        proj_mod.update_project(pid, priority='banana')


def test_list_projects_orders_priority_first(fresh_db):
    from core.knowledge import projects as proj_mod
    importlib.reload(proj_mod)
    a = proj_mod.create_project('low')
    b = proj_mod.create_project('high')
    proj_mod.update_project(b, priority=7)
    rows = proj_mod.list_projects()
    ids = [r['project_id'] for r in rows]
    assert ids.index(b) < ids.index(a)


# S-1E491C8128 ------------------------------------------------------------

def test_tasker_endpoints_register_on_blueprint():
    from frontend.blueprints.tasker_bp import tasker_bp
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(tasker_bp)
    rules = {r.rule for r in app.url_map.iter_rules()}
    must = {
        '/api/tasker/tasks',
        '/api/tasker/registered',
        '/api/tasker/history',
        '/api/tasker/health',
    }
    assert must.issubset(rules), f"missing: {must - rules}"


def test_tasker_history_param_contract(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0
        );
    """)
    conn.execute(
        "INSERT INTO task_run_log (task_name, status, run_at) "
        "VALUES ('a','ok','2026-05-01 10:00:00')")
    conn.commit(); conn.close()

    from frontend.blueprints import tasker_bp as tb
    monkeypatch.setattr(tb, '_get_conn', lambda: sqlite3.connect(str(db)))

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(tb.tasker_bp)
    client = app.test_client()
    # All filters together return JSON list (or empty list, never error)
    r = client.get('/api/tasker/history?task=missing&status=ok&since=2026-01-01&limit=5')
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


# S-247F1ED2E4 ------------------------------------------------------------

def test_research_endpoints_register_on_blueprint():
    from frontend.blueprints.research import research_bp
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(research_bp)
    rules = {r.rule for r in app.url_map.iter_rules()}
    must = {
        '/api/research/start',
        '/api/research/sessions',
        '/api/research/<int:session_id>',
        '/api/research/<int:session_id>/resume',
        '/api/research/<int:session_id>/evidence',
    }
    assert must.issubset(rules), f"missing: {must - rules}"


def test_research_start_rejects_empty_body():
    from frontend.blueprints.research import research_bp
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(research_bp)
    client = app.test_client()
    r = client.post('/api/research/start', json={})
    # Must be a 4xx — don't 500 on missing input
    assert 400 <= r.status_code < 500, f"expected 4xx, got {r.status_code}"


# S-1C7E3AC503 ------------------------------------------------------------

def test_listener_restart_runbook_exists():
    runbook = ROOT / 'docs' / 'runbooks' / 'listener-restart-timeout.md'
    assert runbook.is_file()
    body = runbook.read_text()
    # Required sections to qualify as a real runbook
    for needle in ('Symptom', 'Quick triage', 'Restart sequence',
                   'Root-cause checks', 'When to escalate', 'Verification'):
        assert needle in body, f"runbook missing section: {needle}"
