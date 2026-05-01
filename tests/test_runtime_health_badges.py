"""Smoke tests for the runtime-gateway health badges.

Covers project P-00221285D1 step
``STEP-LOCALAI-RUNTIME-HEALTH-BADGES-20260430``:

  * ``/api/ollama/runtime/health`` returns a stable shape.
  * ``core.model_runtime_gateway.ollama_health`` classifies stuck/stopping
    models as ``degraded`` and unreachable as ``down``.
  * The Local AI and Agents templates expose the badge slots that
    ``localai.js`` / ``access.js`` write into.
  * ``localai.js`` defines and exports ``localaiRuntimeHealthRefresh`` and
    ``access.js`` calls it from ``agentsLocalAIRefresh``.
"""

from __future__ import annotations

import pathlib

import pytest

from core import model_runtime_gateway as gw


REPO = pathlib.Path(__file__).resolve().parents[1]


def test_ollama_health_healthy_no_models():
    snap = gw.ollama_health(ps_payload={"models": []})
    assert snap["ok"] is True
    assert snap["status"] == "healthy"
    assert snap["models"] == []
    assert snap["warnings"] == []


def test_ollama_health_degraded_when_stopping():
    payload = {
        "models": [
            {"model": "llama3.2:3b", "expires_at": "2026-04-30T10:00:00Z",
             "state": "stopping"},
        ]
    }
    snap = gw.ollama_health(ps_payload=payload)
    assert snap["status"] == "degraded"
    assert snap["models"][0]["state"] == "stopping"
    assert any("stuck" in w or "stopping" in w for w in snap["warnings"])


def test_ollama_health_down_when_unreachable(monkeypatch):
    class _Boom(Exception):
        pass

    def _raise(*_a, **_kw):
        raise _Boom("connection refused")

    monkeypatch.setattr(gw.requests, "get", _raise)
    snap = gw.ollama_health(base_url="http://127.0.0.1:0")
    assert snap["ok"] is False
    assert snap["status"] == "down"
    assert snap["warnings"] and "unreachable" in snap["warnings"][0]


def test_runtime_health_endpoint_shape():
    from frontend.terminal import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/api/ollama/runtime/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    for key in ("ok", "status", "models", "warnings"):
        assert key in data, f"missing key: {key}"
    assert data["status"] in {"healthy", "degraded", "down"}


def test_localai_template_has_runtime_badge_slots():
    html = (REPO / "frontend" / "templates" / "terminal_base.html").read_text()
    # Local AI tile
    assert 'id="localai-runtime-badge"' in html
    assert 'id="localai-runtime-warnings"' in html
    # Agents → Local AI tab
    assert 'id="agents-ollama-runtime"' in html
    assert 'id="agents-ollama-warnings"' in html


def test_localai_js_defines_runtime_helper():
    js = (REPO / "frontend" / "static" / "js" / "views" / "localai.js").read_text()
    assert "function localaiRuntimeHealthRefresh(" in js
    assert "/api/ollama/runtime/health" in js
    # Helper exposed globally so other views can call it.
    assert "window.localaiRuntimeHealthRefresh = localaiRuntimeHealthRefresh" in js
    # Local AI refresh path actually calls it.
    assert "localaiRuntimeHealthRefresh('localai-runtime-badge'" in js


def test_agents_view_uses_runtime_helper():
    js = (REPO / "frontend" / "static" / "js" / "views" / "access.js").read_text()
    assert "localaiRuntimeHealthRefresh('agents-ollama-runtime'" in js


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
