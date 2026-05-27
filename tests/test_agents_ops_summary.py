from __future__ import annotations

import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "frontend" / "templates" / "terminal_base.html").read_text(encoding="utf-8")
ACCESS = (ROOT / "frontend" / "static" / "js" / "views" / "access.js").read_text(encoding="utf-8")


def test_agents_template_has_operator_tabs():
    assert 'id="agents-tab-overview"' in TEMPLATE
    assert 'id="agents-tab-queue"' in TEMPLATE
    assert 'id="agents-tab-runtimes"' in TEMPLATE
    assert 'id="agents-tab-configure"' in TEMPLATE
    assert 'id="agents-summary-strip"' in TEMPLATE
    assert 'id="agents-ops-board"' in TEMPLATE
    assert 'id="agents-runtimes-panel"' in TEMPLATE


def test_agents_tile_uses_ops_summary_and_keeps_lifecycle_out_of_cards():
    assert "fetch('/api/agents/ops-summary')" in ACCESS
    assert "function agentsRenderOpsOverview" in ACCESS
    assert "function agentsRenderOpsQueue" in ACCESS
    assert "function agentsRenderOpsRuntimes" in ACCESS
    overview_body = ACCESS.split("function agentsRenderOpsOverview", 1)[1].split("function agentsRenderOpsDetail", 1)[0]
    assert "Decommission" not in overview_body
    assert "Delete" not in overview_body


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "agents_ops.db")
    hive_db = str(tmp_path / "hive.db")
    monkeypatch.setenv("SWARM_DB", db)
    monkeypatch.setenv("SWARM_DB_PATH", db)
    monkeypatch.setenv("SWARM_HIVE_DB", hive_db)
    monkeypatch.setenv("SWARM_HIVE_TOKENS", str(tmp_path / "tokens.jsonl"))
    import utils.db._connection as conn_mod
    conn_mod.DB_PATH = db
    import core.hive.registry as hive_registry
    hive_registry.reset_singleton()
    from frontend.terminal import create_app
    app = create_app()
    app.testing = True
    with app.test_client() as c:
        yield c


def test_agents_ops_summary_endpoint_degrades_to_json(client):
    rv = client.get("/api/agents/ops-summary")
    assert rv.status_code in (200, 500)
    data = rv.get_json()
    assert isinstance(data, dict)
    assert {"summary", "agents", "runtimes", "jobs", "nodes", "blockers"} <= set(data)
    if rv.status_code == 200:
      assert data["ok"] is True
      assert isinstance(data["agents"], list)
      assert isinstance(data["blockers"], list)
