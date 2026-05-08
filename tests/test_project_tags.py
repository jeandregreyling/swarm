"""Tests for project tags (S-4BCE8CF667).

Covers normalization, persistence, decoding, listing filter, and the
API surface (`tags` on POST + `?tag=` on GET).
"""
from __future__ import annotations

import importlib
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
    from utils.db import _connection
    importlib.reload(_connection)
    from utils.db import _schema
    importlib.reload(_schema)
    _schema.initialise_database()
    from core.knowledge import projects as kc_projects
    importlib.reload(kc_projects)
    from frontend.blueprints import knowledge_bp as kbp
    importlib.reload(kbp)
    app = Flask(__name__)
    app.register_blueprint(kbp.knowledge_bp)
    app.config["TESTING"] = True
    return app.test_client(), kc_projects


def test_normalize_tags_accepts_list_string_csv():
    from core.knowledge import projects as kc
    assert kc._normalize_tags(["AI", "research", "AI"]) == ["ai", "research"]
    assert kc._normalize_tags("ai, infra, ai") == ["ai", "infra"]
    assert kc._normalize_tags('["alpha","Beta"]') == ["alpha", "beta"]
    assert kc._normalize_tags(None) == []
    assert kc._normalize_tags("") == []


def test_normalize_tags_strips_blanks_and_caps_length():
    from core.knowledge import projects as kc
    long = ["t" + str(i) for i in range(50)]
    out = kc._normalize_tags(long + ["", "  ", "ok-tag"])
    assert len(out) == 24


def test_create_project_persists_tags(projects_client):
    client, kc = projects_client
    r = client.post(
        "/api/knowledge/projects",
        json={"name": "Tagged", "tags": ["AI", "infra"]},
    )
    assert r.status_code == 200
    pid = r.get_json()["project_id"]
    detail = client.get(f"/api/knowledge/projects/{pid}").get_json()["project"]
    assert detail["tags"] == ["ai", "infra"]


def test_list_decodes_tags(projects_client):
    client, kc = projects_client
    client.post("/api/knowledge/projects", json={"name": "A", "tags": ["red"]})
    client.post("/api/knowledge/projects", json={"name": "B", "tags": "blue,green"})
    items = client.get("/api/knowledge/projects").get_json()["items"]
    by_name = {it["name"]: it["tags"] for it in items}
    assert by_name["A"] == ["red"]
    assert sorted(by_name["B"]) == ["blue", "green"]


def test_list_filters_by_tag(projects_client):
    client, kc = projects_client
    client.post("/api/knowledge/projects", json={"name": "A", "tags": ["red"]})
    client.post("/api/knowledge/projects", json={"name": "B", "tags": ["blue"]})
    client.post("/api/knowledge/projects", json={"name": "C", "tags": ["red", "blue"]})
    red = client.get("/api/knowledge/projects?tag=red").get_json()["items"]
    names = sorted(it["name"] for it in red)
    assert names == ["A", "C"]
    blue = client.get("/api/knowledge/projects?tag=BLUE").get_json()["items"]
    blue_names = sorted(it["name"] for it in blue)
    assert blue_names == ["B", "C"]


def test_patch_project_updates_tags(projects_client):
    client, kc = projects_client
    pid = client.post("/api/knowledge/projects", json={"name": "Edit me"}).get_json()["project_id"]
    r = client.patch(f"/api/knowledge/projects/{pid}", json={"tags": ["alpha", "beta"]})
    assert r.status_code == 200
    detail = client.get(f"/api/knowledge/projects/{pid}").get_json()["project"]
    assert detail["tags"] == ["alpha", "beta"]
    # Replace with empty list — must clear.
    client.patch(f"/api/knowledge/projects/{pid}", json={"tags": []})
    detail2 = client.get(f"/api/knowledge/projects/{pid}").get_json()["project"]
    # update_project drops None values; [] is not None, so it should clear.
    assert detail2["tags"] == []


def test_create_with_no_tags_returns_empty_list(projects_client):
    client, kc = projects_client
    pid = client.post("/api/knowledge/projects", json={"name": "Plain"}).get_json()["project_id"]
    detail = client.get(f"/api/knowledge/projects/{pid}").get_json()["project"]
    assert detail["tags"] == []
