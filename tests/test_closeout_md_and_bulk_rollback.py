"""Closeout markdown export + bulk rollback safety + content-type expansion.

Covers:
  * S-4DB57C3A23 — closeout markdown export
  * S-EECAFCA218 — rollback safety for bulk project import
  * S-9B3CC851A2 — endpoint content-type test expansion
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm_memory.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setenv("SWARM_ROOT", str(ROOT))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from utils.db import _connection
    importlib.reload(_connection)
    from utils.db import _schema
    importlib.reload(_schema)
    _schema.initialise_database()
    from core.knowledge import projects as kc
    importlib.reload(kc)
    from core.knowledge import close_out as co
    importlib.reload(co)
    from frontend.blueprints import knowledge_bp as kbp
    importlib.reload(kbp)
    app = Flask(__name__)
    app.register_blueprint(kbp.knowledge_bp)
    app.config["TESTING"] = True
    return app.test_client(), kc, co


# ── S-4DB57C3A23: closeout markdown export ──────────────────────────────────

def test_render_markdown_failure_payload(env):
    _, _, co = env
    md = co.render_markdown({"ok": False, "error": "nope"})
    assert "# Close-out export failed" in md
    assert "nope" in md


def test_render_markdown_smoke(env):
    client, kc, co = env
    pid = client.post("/api/knowledge/projects", json={"name": "Demo"}).get_json()["project_id"]
    sid = client.post(f"/api/knowledge/projects/{pid}/steps", json={"title": "alpha"}).get_json()["step_id"]
    rep = co.build_report(pid)
    md = co.render_markdown(rep)
    assert md.startswith("# Close-out — Demo")
    assert "## Totals" in md
    assert "## Steps (1)" in md
    assert sid in md
    assert "alpha" in md


def test_endpoint_returns_markdown_when_format_md(env):
    client, kc, _ = env
    pid = client.post("/api/knowledge/projects", json={"name": "MD"}).get_json()["project_id"]
    client.post(f"/api/knowledge/projects/{pid}/steps", json={"title": "s1"})
    r = client.get(f"/api/knowledge/projects/{pid}/close-out?format=md")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/markdown")
    body = r.get_data(as_text=True)
    assert body.startswith("# Close-out")


def test_endpoint_md_for_unknown_project_is_404(env):
    client, _, _ = env
    r = client.get("/api/knowledge/projects/P-NOPE/close-out?format=md")
    assert r.status_code == 404
    assert "failed" in r.get_data(as_text=True).lower()


# ── S-EECAFCA218: rollback safety for bulk import ──────────────────────────

def test_bulk_add_steps_atomic_happy_path(env):
    client, kc, _ = env
    pid = client.post("/api/knowledge/projects", json={"name": "B1"}).get_json()["project_id"]
    res = kc.bulk_add_steps(pid, [{"title": "a"}, {"title": "b"}, {"title": "c"}])
    assert res["ok"] is True
    assert res["rolled_back"] is False
    assert len(res["created"]) == 3
    assert len(kc.list_steps(pid)) == 3


def test_bulk_add_steps_unknown_project(env):
    _, kc, _ = env
    res = kc.bulk_add_steps("P-DOES-NOT-EXIST", [{"title": "a"}])
    assert res["ok"] is False
    assert "unknown" in res["error"]
    assert res["created"] == []


def test_bulk_add_steps_atomic_rollback_on_failure(env, monkeypatch):
    client, kc, _ = env
    pid = client.post("/api/knowledge/projects", json={"name": "B2"}).get_json()["project_id"]
    # Seed two existing steps so we can verify they survive the rollback.
    kc.add_step(pid, "pre-existing")
    pre_count = len(kc.list_steps(pid))

    # Inject a failure on the third insert.
    real_uuid4 = __import__("uuid").uuid4
    calls = {"n": 0}
    def boom(*a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated DB failure on row 3")
        return real_uuid4()
    monkeypatch.setattr("core.knowledge.projects.uuid.uuid4", boom)

    items = [{"title": "x1"}, {"title": "x2"}, {"title": "x3"}, {"title": "x4"}]
    res = kc.bulk_add_steps(pid, items, atomic=True)
    assert res["ok"] is False
    assert res["rolled_back"] is True
    assert res["failed"]["reason"].startswith("simulated DB failure")
    assert res["created"] == []
    # Pre-existing row remains; none of x1..x4 should have been persisted.
    titles = {s["title"] for s in kc.list_steps(pid)}
    assert titles == {"pre-existing"}
    assert len(kc.list_steps(pid)) == pre_count


def test_bulk_add_steps_skips_duplicates_within_batch(env):
    client, kc, _ = env
    pid = client.post("/api/knowledge/projects", json={"name": "B3"}).get_json()["project_id"]
    res = kc.bulk_add_steps(pid, [{"title": "dup"}, {"title": "DUP"}, {"title": "ok"}])
    assert res["ok"] is True
    assert len(res["created"]) == 2
    assert len(res["skipped"]) == 1
    assert res["skipped"][0]["reason"] == "duplicate title"


# ── S-9B3CC851A2: endpoint content-type expansion ──────────────────────────

def test_json_endpoints_advertise_application_json(env):
    client, kc, _ = env
    pid = client.post("/api/knowledge/projects", json={"name": "CT"}).get_json()["project_id"]
    sid = client.post(f"/api/knowledge/projects/{pid}/steps", json={"title": "ct"}).get_json()["step_id"]

    json_routes = (
        "/api/knowledge/projects",
        f"/api/knowledge/projects/{pid}",
        f"/api/knowledge/projects/{pid}/steps",
        f"/api/knowledge/projects/{pid}/close-out",
        f"/api/knowledge/steps/{sid}/dependencies",
    )
    for route in json_routes:
        r = client.get(route)
        assert r.status_code == 200, f"{route} -> {r.status_code}"
        ct = r.headers["Content-Type"]
        assert ct.startswith("application/json"), f"{route} -> {ct}"


def test_markdown_export_advertises_markdown_content_type(env):
    client, _, _ = env
    pid = client.post("/api/knowledge/projects", json={"name": "MD2"}).get_json()["project_id"]
    r = client.get(f"/api/knowledge/projects/{pid}/close-out?format=md")
    assert r.headers["Content-Type"].startswith("text/markdown")
