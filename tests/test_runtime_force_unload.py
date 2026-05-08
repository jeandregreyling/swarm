"""Tests for runtime gateway force_unload + endpoint (PACKET-05 stuck runner)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import model_runtime_gateway as gw


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _ps_payload(state=None):
    if state is None:
        return {"models": []}
    return {
        "models": [
            {"model": "llama3.2", "expires_at": "soon", "state": state, "size": 1},
        ]
    }


def test_force_unload_clean(monkeypatch):
    posts = []

    def fake_post(url, json=None, timeout=None):
        posts.append((url, json))
        return _FakeResp({"ok": True})

    # ps returns empty (model already gone after unload)
    def fake_get(url, timeout=None):
        return _FakeResp(_ps_payload(None))

    monkeypatch.setattr(gw.requests, "post", fake_post)
    monkeypatch.setattr(gw.requests, "get", fake_get)
    monkeypatch.setattr(gw.time, "sleep", lambda *_: None)

    snap = gw.force_unload("llama3.2", poll_seconds=2, poll_interval_s=0.1)
    assert snap["ok"] is True
    assert snap["action"] == "unloaded"
    assert snap["stuck"] is False
    assert posts and posts[0][1]["keep_alive"] == 0


def test_force_unload_stuck_recovers_via_restart(monkeypatch):
    # Model keeps reporting stopping until restart command is invoked.
    state = {"restarted": False}

    def fake_post(url, json=None, timeout=None):
        return _FakeResp({"ok": True})

    def fake_get(url, timeout=None):
        if state["restarted"]:
            return _FakeResp(_ps_payload(None))
        return _FakeResp(_ps_payload("stopping"))

    def fake_runner(cmd):
        state["restarted"] = True
        return 0, "ok"

    monkeypatch.setattr(gw.requests, "post", fake_post)
    monkeypatch.setattr(gw.requests, "get", fake_get)
    monkeypatch.setattr(gw.time, "sleep", lambda *_: None)

    snap = gw.force_unload(
        "llama3.2",
        poll_seconds=2,
        poll_interval_s=0.1,
        restart_cmds=[["systemctl", "restart", "ollama"]],
        subprocess_runner=fake_runner,
    )
    assert snap["ok"] is True
    assert snap["action"] == "restarted"
    assert snap["stuck"] is True
    assert any(step.get("step") == "restart" and step.get("code") == 0 for step in snap["attempted"])


def test_force_unload_stuck_needs_operator(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _FakeResp({"ok": True})

    def fake_get(url, timeout=None):
        return _FakeResp(_ps_payload("stopping"))

    def fake_runner(cmd):
        return 1, "Failed to restart ollama.service: Interactive authentication required."

    monkeypatch.setattr(gw.requests, "post", fake_post)
    monkeypatch.setattr(gw.requests, "get", fake_get)
    monkeypatch.setattr(gw.time, "sleep", lambda *_: None)

    snap = gw.force_unload(
        "llama3.2",
        poll_seconds=2,
        poll_interval_s=0.1,
        restart_cmds=[["systemctl", "--user", "restart", "ollama"]],
        subprocess_runner=fake_runner,
    )
    assert snap["ok"] is False
    assert snap["action"] == "needs_operator"
    assert "sudo systemctl restart ollama" in snap["message"]


def test_force_unload_requires_model_name():
    snap = gw.force_unload("")
    assert snap["ok"] is False
    assert snap["action"] == "noop"


def test_force_unload_endpoint_returns_snapshot(monkeypatch):
    from frontend.terminal import create_app

    def fake_force_unload(model):
        return {
            "ok": True,
            "model": model,
            "stuck": False,
            "action": "unloaded",
            "attempted": [{"step": "unload", "ok": True}],
            "message": f"{model} unloaded cleanly",
        }

    monkeypatch.setattr(
        "core.model_runtime_gateway.force_unload",
        fake_force_unload,
    )

    client = create_app().test_client()
    resp = client.post(
        "/api/ollama/runtime/force-unload",
        data=json.dumps({"model": "llama3.2"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["action"] == "unloaded"
    assert body["model"] == "llama3.2"


def test_force_unload_endpoint_requires_model():
    from frontend.terminal import create_app

    client = create_app().test_client()
    resp = client.post(
        "/api/ollama/runtime/force-unload",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False


def test_localai_js_exposes_force_unload():
    src = Path("frontend/static/js/views/localai.js").read_text(encoding="utf-8")
    assert "/api/ollama/runtime/force-unload" in src
    assert "function localaiRuntimeForceUnload(" in src
    assert "window.localaiRuntimeForceUnload = localaiRuntimeForceUnload" in src
    # The badge must surface a Force unload button when a model is stuck.
    assert "Force unload" in src
