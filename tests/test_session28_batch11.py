"""Regression tests for backlog batch 11 (2026-05-02 session 28).

- S-0F9BA7EF34: bulk backlog import endpoint
- S-1DC62BD77B: Studio project search endpoint
- S-1D88D439EE05: chat_smoke_probe registered task
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


@pytest.fixture()
def client(fresh_db):
    from core.knowledge import projects as proj_mod
    importlib.reload(proj_mod)
    proj_mod._SCHEMA_READY = False
    proj_mod._ensure_schema()

    from frontend.blueprints import knowledge_bp as kb_mod
    importlib.reload(kb_mod)

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(kb_mod.knowledge_bp)
    return app.test_client(), proj_mod


# S-0F9BA7EF34 -------------------------------------------------------------

def test_bulk_import_creates_steps(client):
    c, proj_mod = client
    pid = proj_mod.create_project('bulk demo')
    r = c.post(f'/api/knowledge/projects/{pid}/steps/bulk',
               json={'steps': [
                   {'title': 'a'}, {'title': 'b'}, {'title': 'c'},
               ]})
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] and body['created_count'] == 3 and body['skipped_count'] == 0
    assert len(proj_mod.list_steps(pid)) == 3


def test_bulk_import_dedupes_titles(client):
    c, proj_mod = client
    pid = proj_mod.create_project('dedupe demo')
    proj_mod.add_step(pid, 'already')
    r = c.post(f'/api/knowledge/projects/{pid}/steps/bulk',
               json={'steps': [{'title': 'already'}, {'title': 'new'}]})
    body = r.get_json()
    assert body['created_count'] == 1
    assert body['skipped_count'] == 1
    assert body['skipped'][0]['reason'] == 'duplicate title'


def test_bulk_import_rejects_empty_payload(client):
    c, proj_mod = client
    pid = proj_mod.create_project('e')
    r = c.post(f'/api/knowledge/projects/{pid}/steps/bulk', json={'steps': []})
    assert r.status_code == 400


def test_bulk_import_rejects_oversized_batch(client):
    c, proj_mod = client
    pid = proj_mod.create_project('big')
    r = c.post(f'/api/knowledge/projects/{pid}/steps/bulk',
               json={'steps': [{'title': f't{i}'} for i in range(501)]})
    assert r.status_code == 400


def test_bulk_import_404_for_unknown_project(client):
    c, _ = client
    r = c.post('/api/knowledge/projects/P-NOPE/steps/bulk',
               json={'steps': [{'title': 'x'}]})
    assert r.status_code == 404


# S-1DC62BD77B -------------------------------------------------------------

def test_search_finds_by_name(client):
    c, proj_mod = client
    proj_mod.create_project('Alpha widget')
    proj_mod.create_project('Beta gizmo')
    r = c.get('/api/knowledge/projects/search?q=widg')
    body = r.get_json()
    assert r.status_code == 200 and body['ok']
    assert body['count'] == 1
    assert body['items'][0]['name'] == 'Alpha widget'


def test_search_finds_by_description(client):
    c, proj_mod = client
    proj_mod.create_project('p1', description='secret-marker')
    r = c.get('/api/knowledge/projects/search?q=secret-marker')
    body = r.get_json()
    assert body['count'] == 1


def test_search_short_query_rejected(client):
    c, _ = client
    r = c.get('/api/knowledge/projects/search?q=a')
    assert r.status_code == 400


def test_search_orders_by_priority_desc(client):
    c, proj_mod = client
    a = proj_mod.create_project('match low')
    b = proj_mod.create_project('match high')
    proj_mod.update_project(b, priority=5)
    r = c.get('/api/knowledge/projects/search?q=match')
    items = r.get_json()['items']
    assert items[0]['project_id'] == b
    assert items[1]['project_id'] == a


# S-1D88D439EE05 -----------------------------------------------------------

def test_chat_smoke_probe_registered():
    from fridays.task_runner import TASK_REGISTRY
    assert 'chat_smoke_probe' in TASK_REGISTRY
    entry = TASK_REGISTRY['chat_smoke_probe']
    assert entry['category'] == 'monitoring'
    assert callable(entry['fn'])


def test_chat_smoke_probe_handles_orchestrator_failure(monkeypatch, fresh_db):
    # Pre-create the log table so the helper can persist its result.
    conn = sqlite3.connect(fresh_db)
    conn.execute("""
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0
        )""")
    conn.commit(); conn.close()

    # Force an exception in the orchestrator dependency.
    import sys as _sys
    fake = type(_sys)('fridays.orchestrator')
    def _boom(*a, **kw):
        raise RuntimeError('llm offline')
    fake.ask_agent = _boom
    monkeypatch.setitem(_sys.modules, 'fridays.orchestrator', fake)
    # If the parent package has been imported earlier in this test session,
    # `from fridays import orchestrator` will resolve via getattr(fridays,
    # 'orchestrator') and bypass our sys.modules override. Patch the
    # attribute directly so the override survives test ordering.
    try:
        import fridays as _frpkg
        monkeypatch.setattr(_frpkg, 'orchestrator', fake, raising=False)
    except ImportError:
        pass

    from fridays.task_runner import TASK_REGISTRY
    out = TASK_REGISTRY['chat_smoke_probe']['fn']()
    assert 'FAILED' in out and 'llm offline' in out

    conn = sqlite3.connect(fresh_db)
    row = conn.execute(
        "SELECT status FROM task_run_log WHERE task_name='chat_smoke_probe'"
    ).fetchone()
    conn.close()
    assert row and row[0] == 'error'
