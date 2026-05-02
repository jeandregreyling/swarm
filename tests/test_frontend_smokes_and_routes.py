"""Frontend smoke + route registration + closeout evidence tests.

Covers:
  * S-B414D698F6 — frontend smoke for Tasker view
  * S-AC957DB4D4 — frontend smoke for Studio project backlog
  * S-5956725121 — route registration test
  * S-6D020171A4 — project closeout evidence shape pinned
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_BASE = ROOT / "frontend" / "templates" / "terminal_base.html"


# ── S-B414D698F6: Tasker view smoke ─────────────────────────────────────────

def test_tasker_view_dom_anchors_present():
    src = TERMINAL_BASE.read_text(encoding="utf-8")
    expected_ids = (
        "tasker-list", "tasker-stat-total", "tasker-stat-active",
        "tasker-stat-disabled",
    )
    for anchor in expected_ids:
        assert f'id="{anchor}"' in src, f"missing tasker anchor: {anchor}"


def test_tasker_js_included_with_cachebust():
    src = TERMINAL_BASE.read_text(encoding="utf-8")
    assert '/static/js/views/tasker.js?v={{ ASSET_VERSION }}' in src, (
        "tasker.js script tag must be included with the global "
        "ASSET_VERSION cache-bust token"
    )


# ── S-AC957DB4D4: Studio project backlog smoke ──────────────────────────────

def test_studio_projects_panel_anchors_present():
    src = TERMINAL_BASE.read_text(encoding="utf-8")
    expected_ids = (
        "studio-projects-panel", "projects-new-name", "projects-summary",
    )
    for anchor in expected_ids:
        assert f'id="{anchor}"' in src, f"missing studio anchor: {anchor}"


def test_studio_js_included_with_cachebust():
    src = TERMINAL_BASE.read_text(encoding="utf-8")
    assert '/static/js/views/studio.js?v={{ ASSET_VERSION }}' in src


# ── S-5956725121: route registration sanity ─────────────────────────────────

@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_DB_PATH", str(tmp_path / "swarm.db"))
    monkeypatch.setenv("SWARM_ROOT", str(ROOT))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(ROOT / "frontend") not in sys.path:
        sys.path.insert(0, str(ROOT / "frontend"))
    from frontend import terminal as t
    importlib.reload(t)
    return t.create_app()


def test_create_app_registers_many_blueprints(isolated_app):
    bps = list(isolated_app.blueprints.keys())
    assert len(bps) >= 50, (
        f"Expected at least 50 blueprints registered, got {len(bps)}: {bps[:10]}..."
    )


def test_create_app_registers_critical_routes(isolated_app):
    rules = {r.rule for r in isolated_app.url_map.iter_rules()}
    must_have = (
        "/api/knowledge/projects",
        "/api/knowledge/projects/<project_id>",
        "/api/knowledge/projects/<project_id>/steps",
        "/api/knowledge/projects/<project_id>/steps/bulk",
        "/api/knowledge/projects/<project_id>/close-out",
        "/api/knowledge/steps/<step_id>/dependencies",
        "/api/ollama/runtime/health",
        "/api/ollama/runtime/force-unload",
    )
    missing = [r for r in must_have if r not in rules]
    assert not missing, f"missing critical routes: {missing}"


def test_app_exposes_asset_version_to_templates(isolated_app):
    with isolated_app.test_request_context("/"):
        # Render a tiny inline template using the context processor.
        from flask import render_template_string
        out = render_template_string("{{ ASSET_VERSION }}")
        assert out.strip(), "ASSET_VERSION must not be empty"


# ── S-6D020171A4: closeout evidence shape ──────────────────────────────────

def _seed_project_with_evidence(client, kc):
    pid = client.post("/api/knowledge/projects", json={"name": "Cleared"}).get_json()["project_id"]
    sid = client.post(f"/api/knowledge/projects/{pid}/steps", json={"title": "step-A"}).get_json()["step_id"]
    cid = kc.add_test_case(pid, "case-A", step_id=sid)
    kc.update_step_status(sid, "done")
    return pid, sid, cid


@pytest.fixture
def projects_env(tmp_path, monkeypatch):
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


def test_close_out_report_shape(projects_env):
    client, kc, co = projects_env
    pid, sid, cid = _seed_project_with_evidence(client, kc)
    rep = co.build_report(pid)
    assert rep["ok"] is True
    assert rep["project_id"] == pid
    assert "totals" in rep and rep["totals"]["steps"] >= 1
    assert isinstance(rep["steps"], list) and rep["steps"]
    s0 = rep["steps"][0]
    for key in ("step_id", "title", "status", "test_files", "cases", "verdict"):
        assert key in s0
    assert isinstance(s0["test_files"], list)
    assert isinstance(s0["cases"], list)


def test_close_out_unknown_project_returns_error(projects_env):
    client, kc, co = projects_env
    rep = co.build_report("P-DOES-NOT-EXIST")
    assert rep.get("ok") is False
    assert "not found" in rep.get("error", "").lower()


def test_close_out_endpoint_returns_report(projects_env):
    client, kc, co = projects_env
    pid, _, _ = _seed_project_with_evidence(client, kc)
    r = client.get(f"/api/knowledge/projects/{pid}/close-out")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("ok") is True
    assert body.get("project_id") == pid
    assert "steps" in body and isinstance(body["steps"], list)
