"""Session 30 — ALM test-run persistence and endpoint tests.

TARGETED test file (Session 30 QA directive): run ONLY this + test_spine +
test_knowledge instead of the 700+ regression.
"""
from __future__ import annotations

import time
import pytest


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point DB_PATH at a temp sqlite, reset cached module state."""
    from utils.db import _connection as conn_mod
    db_path = tmp_path / "test_runs.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    # Force re-resolve in the connection module
    monkeypatch.setattr(conn_mod, "DB_PATH", str(db_path), raising=False)
    # Reset module schema flag so it recreates against the temp DB
    import core.knowledge.test_runs as tr
    monkeypatch.setattr(tr, "_SCHEMA_READY", False, raising=False)
    yield db_path


# ── Persistence layer ───────────────────────────────────────────────────────

def test_start_run_returns_id(isolated_db):
    from core.knowledge import test_runs as tr
    run_id = tr.start_run("pytest:spine", change_id="CR-001", command="pytest tests/test_spine.py")
    assert run_id
    assert len(run_id) == 16


def test_start_run_rejects_empty_script_id(isolated_db):
    from core.knowledge import test_runs as tr
    assert tr.start_run("") is None


def test_finish_run_sets_status_and_duration(isolated_db):
    from core.knowledge import test_runs as tr
    run_id = tr.start_run("pytest:spine", change_id="CR-002")
    time.sleep(0.01)
    ok = tr.finish_run(run_id, status=tr.STATUS_PASS, exit_code=0, stdout_tail="716 passed")
    assert ok
    run = tr.get_run(run_id)
    assert run["status"] == "pass"
    assert run["exit_code"] == 0
    assert run["duration_ms"] >= 1
    assert "716 passed" in run["stdout_tail"]


def test_finish_run_records_scorecard_for_linked_proposal(isolated_db):
    from core import agent_scorecards
    from core.knowledge import test_runs as tr
    from utils.db._connection import get_connection

    with get_connection() as conn:
        conn.execute(
            """CREATE TABLE work_proposals (
                proposal_id TEXT PRIMARY KEY,
                ticket_number TEXT DEFAULT '',
                title TEXT DEFAULT '',
                agent TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            """INSERT INTO work_proposals
               (proposal_id, title, agent)
               VALUES ('P-RUN-1', 'Implement integration upgrade', 'ten')"""
        )
        conn.commit()

    run_id = tr.start_run("pytest:focused", change_id="P-RUN-1")
    assert tr.finish_run(run_id, status=tr.STATUS_PASS, exit_code=0, stdout_tail="passed")

    testing = agent_scorecards.list_scorecards(capability="testing", agents=["ten"], limit=1)[0]
    coding = agent_scorecards.list_scorecards(capability="coding", agents=["ten"], limit=1)[0]
    assert testing["source"] == "testlab:run"
    assert coding["source"] == "testlab:run"


def test_finish_run_unknown_status_coerces_to_fail(isolated_db):
    from core.knowledge import test_runs as tr
    run_id = tr.start_run("pytest:foo")
    tr.finish_run(run_id, status="bogus")
    run = tr.get_run(run_id)
    assert run["status"] == "fail"


def test_finish_run_missing_row_returns_false(isolated_db):
    from core.knowledge import test_runs as tr
    assert tr.finish_run("does-not-exist", status=tr.STATUS_PASS) is False


def test_add_artifact_and_get_run(isolated_db):
    from core.knowledge import test_runs as tr
    run_id = tr.start_run("pytest:spine", change_id="CR-003")
    tr.finish_run(run_id, status=tr.STATUS_PASS, exit_code=0)
    assert tr.add_artifact(run_id, "note", "Investigated flake in SSE reconnect.")
    assert tr.add_artifact(run_id, "log", "pytest output snippet")
    run = tr.get_run(run_id)
    assert len(run["artifacts"]) == 2
    assert run["artifacts"][0]["kind"] == "note"


def test_list_runs_filters_by_change(isolated_db):
    from core.knowledge import test_runs as tr
    r1 = tr.start_run("pytest:a", change_id="CR-X")
    r2 = tr.start_run("pytest:b", change_id="CR-Y")
    tr.finish_run(r1, status=tr.STATUS_PASS)
    tr.finish_run(r2, status=tr.STATUS_FAIL, exit_code=1)
    items_x = tr.list_runs(change_id="CR-X")
    assert len(items_x) == 1
    assert items_x[0]["script_id"] == "pytest:a"
    items_fail = tr.list_runs(status="fail")
    assert len(items_fail) == 1
    assert items_fail[0]["script_id"] == "pytest:b"


def test_list_runs_recent_first(isolated_db):
    from core.knowledge import test_runs as tr
    ids = []
    for i in range(3):
        ids.append(tr.start_run(f"pytest:{i}"))
        time.sleep(0.005)
    items = tr.list_runs(limit=5)
    assert len(items) == 3
    # Most recent first
    assert items[0]["script_id"] == "pytest:2"
    assert items[-1]["script_id"] == "pytest:0"


def test_abort_run(isolated_db):
    from core.knowledge import test_runs as tr
    run_id = tr.start_run("pytest:x")
    assert tr.abort_run(run_id, reason="user stopped")
    run = tr.get_run(run_id)
    assert run["status"] == "aborted"
    assert "user stopped" in (run["stdout_tail"] or "")


# ── API endpoints ───────────────────────────────────────────────────────────

@pytest.fixture
def client(isolated_db, monkeypatch):
    """Minimal Flask app with knowledge_bp only (avoid booting the whole app)."""
    from flask import Flask
    from frontend.blueprints.knowledge_bp import knowledge_bp
    app = Flask(__name__)
    app.register_blueprint(knowledge_bp)
    return app.test_client()


def test_api_start_and_finish_run(client):
    r = client.post("/api/knowledge/test-runs", json={
        "script_id": "pytest:spine",
        "change_id": "CR-API",
        "command": "pytest tests/test_spine.py",
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    run_id = data["run_id"]
    assert run_id

    r = client.patch(f"/api/knowledge/test-runs/{run_id}", json={
        "status": "pass", "exit_code": 0, "stdout_tail": "21 passed",
    })
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    r = client.get(f"/api/knowledge/test-runs/{run_id}")
    assert r.status_code == 200
    run = r.get_json()["run"]
    assert run["status"] == "pass"
    assert run["exit_code"] == 0


def test_api_start_run_requires_script_id(client):
    r = client.post("/api/knowledge/test-runs", json={"change_id": "x"})
    assert r.status_code == 400


def test_api_finish_unknown_returns_404(client):
    r = client.patch("/api/knowledge/test-runs/unknown", json={"status": "pass"})
    assert r.status_code == 404


def test_api_add_artifact_requires_body(client):
    r = client.post("/api/knowledge/test-runs", json={"script_id": "pytest:spine"})
    run_id = r.get_json()["run_id"]
    r = client.post(f"/api/knowledge/test-runs/{run_id}/artifacts", json={"kind": "note"})
    assert r.status_code == 400


def test_api_add_artifact_and_list(client):
    r = client.post("/api/knowledge/test-runs", json={
        "script_id": "pytest:spine", "change_id": "CR-LIST",
    })
    run_id = r.get_json()["run_id"]
    client.post(f"/api/knowledge/test-runs/{run_id}/artifacts",
                json={"kind": "note", "body": "hello world"})
    r = client.get(f"/api/knowledge/test-runs/{run_id}")
    run = r.get_json()["run"]
    assert any(a["body"] == "hello world" for a in run["artifacts"])


def test_api_list_filter_by_change(client):
    client.post("/api/knowledge/test-runs", json={"script_id": "s1", "change_id": "A"})
    client.post("/api/knowledge/test-runs", json={"script_id": "s2", "change_id": "B"})
    r = client.get("/api/knowledge/test-runs?change_id=A")
    data = r.get_json()
    assert data["ok"] is True
    assert all(item["change_id"] == "A" for item in data["items"])
    assert len(data["items"]) == 1


def test_api_get_unknown_returns_404(client):
    r = client.get("/api/knowledge/test-runs/does-not-exist")
    assert r.status_code == 404
