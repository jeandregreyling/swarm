"""API contract tests for /api/knowledge/projects endpoints.

Covers PACKET-05 S-6763C8B59C: create / list / detail / patch / steps /
bulk steps / test cases / link-proposal / blackboard / search / delete
through the Flask test_client.

Each test runs against an isolated, freshly-initialised SQLite DB so we
exercise the real schema, real blueprint, real handler — only the DB
file is swapped.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def projects_client(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm_memory.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setenv("SWARM_ROOT", str(ROOT))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # Reload the connection module so it picks up our env override.
    from utils.db import _connection
    importlib.reload(_connection)
    # And the schema module so the (new) connection module is used.
    from utils.db import _schema
    importlib.reload(_schema)
    _schema.initialise_database()

    # Reload knowledge modules that captured a reference to the connection.
    from core.knowledge import projects as kc_projects
    importlib.reload(kc_projects)
    from frontend.blueprints import knowledge_bp as kbp
    importlib.reload(kbp)

    app = Flask(__name__)
    app.register_blueprint(kbp.knowledge_bp)
    app.config["TESTING"] = True
    return app.test_client()


def _create_project(client, name="Contract Project", methodology="agile"):
    r = client.post(
        "/api/knowledge/projects",
        json={"name": name, "methodology": methodology, "owner": "seven"},
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json()["project_id"]


def test_create_project_requires_name(projects_client):
    r = projects_client.post("/api/knowledge/projects", json={})
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False
    assert "name" in body["error"]


def test_create_and_list_project(projects_client):
    pid = _create_project(projects_client, name="Apollo")
    r = projects_client.get("/api/knowledge/projects?limit=50")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert any(item.get("project_id") == pid for item in body["items"])


def test_project_detail_shape(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.get(f"/api/knowledge/projects/{pid}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    proj = body["project"]
    for key in ("project_id", "name", "steps", "test_cases", "blackboard_notes"):
        assert key in proj


def test_project_detail_404_for_unknown(projects_client):
    r = projects_client.get("/api/knowledge/projects/P-DOES-NOT-EXIST")
    assert r.status_code == 404


def test_project_patch_updates_metadata(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.patch(
        f"/api/knowledge/projects/{pid}",
        json={"description": "patched-desc", "status": "active"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    after = projects_client.get(f"/api/knowledge/projects/{pid}").get_json()["project"]
    assert after["description"] == "patched-desc"
    assert after["status"] == "active"


def test_project_patch_strips_reserved_fields(projects_client):
    """Server-owned fields (project_id, created_at, updated_at) must be ignored
    even if a client tries to send them."""
    pid = _create_project(projects_client)
    r = projects_client.patch(
        f"/api/knowledge/projects/{pid}",
        json={"project_id": "P-HACK", "description": "ok"},
    )
    assert r.status_code == 200
    after = projects_client.get(f"/api/knowledge/projects/{pid}").get_json()["project"]
    assert after["project_id"] == pid


def test_steps_add_and_list(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/steps",
        json={"title": "First", "description": "x"},
    )
    assert r.status_code == 200
    sid = r.get_json()["step_id"]
    listing = projects_client.get(f"/api/knowledge/projects/{pid}/steps").get_json()
    assert listing["ok"] is True
    titles = [item["title"] for item in listing["items"]]
    assert "First" in titles
    assert any(item["step_id"] == sid for item in listing["items"])


def test_step_add_requires_title(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.post(f"/api/knowledge/projects/{pid}/steps", json={})
    assert r.status_code == 400


def test_steps_bulk_create_with_dedupe(projects_client):
    pid = _create_project(projects_client)
    payload = {
        "steps": [
            {"title": "Bulk A"},
            {"title": "Bulk B"},
            {"title": "Bulk A"},  # duplicate within request
            {"description": "missing title"},
            {"title": "Bulk C"},
        ]
    }
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/steps/bulk", json=payload
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["created_count"] == 3
    assert body["skipped_count"] == 2
    skip_reasons = {s.get("reason") for s in body["skipped"]}
    assert "duplicate title" in skip_reasons
    assert "title required" in skip_reasons


def test_steps_bulk_rejects_empty_or_oversized(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/steps/bulk", json={"steps": []}
    )
    assert r.status_code == 400
    huge = {"steps": [{"title": f"S{i}"} for i in range(501)]}
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/steps/bulk", json=huge
    )
    assert r.status_code == 400


def test_steps_bulk_404_for_unknown_project(projects_client):
    r = projects_client.post(
        "/api/knowledge/projects/P-NOPE/steps/bulk",
        json={"steps": [{"title": "x"}]},
    )
    assert r.status_code == 404


def test_test_cases_add_and_list(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/test-cases",
        json={"title": "Smoke"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert "case_id" in body
    listing = projects_client.get(
        f"/api/knowledge/projects/{pid}/test-cases"
    ).get_json()
    assert any(item["title"] == "Smoke" for item in listing["items"])


def test_link_proposal_requires_id(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/link-proposal", json={}
    )
    assert r.status_code == 400


def test_blackboard_add_and_list(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/blackboard",
        json={"content": "first note", "kind": "note"},
    )
    assert r.status_code == 200
    listing = projects_client.get(
        f"/api/knowledge/projects/{pid}/blackboard"
    ).get_json()
    assert listing["ok"] is True
    assert any(n.get("content") == "first note" for n in listing["items"])


def test_blackboard_add_requires_content(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.post(
        f"/api/knowledge/projects/{pid}/blackboard", json={"content": ""}
    )
    assert r.status_code == 400


def test_search_requires_min_query(projects_client):
    r = projects_client.get("/api/knowledge/projects/search?q=a")
    assert r.status_code in (400, 200)
    # If the API chooses 200, body must signal an error. If 400, the
    # error response is canonical. Both are valid contracts.
    body = r.get_json()
    if r.status_code == 200:
        assert body.get("ok") is False or body.get("items") == []


def test_search_returns_matches(projects_client):
    _create_project(projects_client, name="Apollo Mission")
    _create_project(projects_client, name="Voyager Probe")
    r = projects_client.get("/api/knowledge/projects/search?q=apollo")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    names = [item["name"].lower() for item in body["items"]]
    assert any("apollo" in n for n in names)


def test_delete_project(projects_client):
    pid = _create_project(projects_client)
    r = projects_client.delete(f"/api/knowledge/projects/{pid}")
    assert r.status_code == 200
    r = projects_client.get(f"/api/knowledge/projects/{pid}")
    assert r.status_code == 404


def test_delete_unknown_project_404(projects_client):
    r = projects_client.delete("/api/knowledge/projects/P-DOES-NOT-EXIST")
    assert r.status_code == 404
