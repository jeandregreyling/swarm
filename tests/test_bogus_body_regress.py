"""Regression for P-EB07CD8588 'bogus-body' / type-confusion stories.

Pins:
  * S-A9E1B9ED97 — global TypeError/AttributeError guard returns 400 for
                   /api/* requests with a JSON body
  * S-B6F548DCDD — surgical str() coercion on node_register / node_discover
                   / library_ingest survives non-string inputs without 500
  * S-D5071B4DCA — duplicate Vortex checkpoint label returns 409 Conflict
  * S-F96EC5B78A — verify + regression sweep across the bogus payloads
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_DB_PATH", str(tmp_path / "swarm.db"))
    monkeypatch.setenv("SWARM_ROOT", str(ROOT))
    for p in (ROOT, ROOT / "frontend"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from frontend import terminal as t
    importlib.reload(t)
    a = t.create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _no_vortex_git(monkeypatch):
    """Stop POST /api/time/checkpoints from creating real git commits/tags
    during the test sweep — it pollutes history and races the user's
    pending commit message."""
    try:
        from frontend.blueprints import time_wizard_bp as bp_mod
    except Exception:
        return
    monkeypatch.setattr(
        bp_mod.time_wizard, "create_workflow_checkpoint",
        lambda *a, **kw: {"checkpoint_id": 0, "checkpoint_name": "test-noop"},
        raising=True,
    )


# ── S-B6F548DCDD: surgical coercion on node_register ────────────────────────

@pytest.mark.parametrize("payload", [
    {"name": ["nope"], "url": "https://x", "api_key": "k"},        # list
    {"name": {"k": "v"}, "url": "https://x", "api_key": "k"},      # dict
    {"name": 42, "url": "https://x", "api_key": "k"},              # int
    {"name": None, "url": "https://x", "api_key": "k"},            # None
    {"name": "", "url": "", "api_key": ""},                        # empty
])
def test_node_register_rejects_bogus_types_without_500(client, payload):
    r = client.post("/api/node/register", json=payload)
    assert r.status_code in (400, 401, 403, 422), (
        f"bogus payload {payload!r} caused {r.status_code} {r.data[:200]!r}"
    )


@pytest.mark.parametrize("payload", [
    {"url": ["https://x"], "api_key": "k"},
    {"url": 123, "api_key": "k"},
    {"url": None, "api_key": "k"},
    {},
])
def test_node_discover_rejects_bogus_types_without_500(client, payload):
    r = client.post("/api/node/discover", json=payload)
    assert r.status_code in (400, 401, 403, 422, 502), (
        f"bogus payload {payload!r} caused {r.status_code} {r.data[:200]!r}"
    )


# ── S-A9E1B9ED97: global guard converts TypeError→400 on JSON-body APIs ─────

def test_library_ingest_bogus_content_does_not_500(client):
    # content is required; sending a list should not raise to 500
    r = client.post("/api/library/ingest", json={"content": ["a", "b"]})
    assert r.status_code in (400, 401, 403, 422), r.status_code


def test_global_guard_handles_typeerror_on_api_with_body(client):
    """Endpoints that strictly expect string fields must yield 400, never
    bubble TypeError to Flask's default 500 handler when there's a body."""
    # Send a POST to a known JSON endpoint with a junk body — even unknown
    # endpoints under /api/ shouldn't 500 from a TypeError in the request
    # parsing. Try several real endpoints.
    bogus_bodies = [
        {"label": ["x"], "agent": "t", "description": ""},
        {"label": 42},
        {"label": {"nested": True}},
    ]
    for body in bogus_bodies:
        r = client.post("/api/time/checkpoints", json=body)
        # Either accepts the coerced label, or rejects with 4xx — never 500
        assert r.status_code < 500, (
            f"checkpoint POST {body!r} returned {r.status_code} {r.data[:200]!r}"
        )


# ── S-D5071B4DCA: duplicate checkpoint label → 409 ──────────────────────────

def test_duplicate_checkpoint_label_returns_409(client, monkeypatch):
    """The blueprint maps SQLite UNIQUE violations on label collision to
    409 Conflict instead of bubbling as 500."""
    from frontend.blueprints import time_wizard_bp as bp_mod

    def _raise_unique(*a, **kw):
        raise Exception("UNIQUE constraint failed: checkpoints.label")

    monkeypatch.setattr(
        bp_mod.time_wizard, "create_workflow_checkpoint", _raise_unique,
        raising=True,
    )
    r = client.post(
        "/api/time/checkpoints",
        json={"label": "dup-label", "agent": "t", "description": ""},
    )
    assert r.status_code == 409, (r.status_code, r.data[:300])
    body = r.get_json()
    assert body["ok"] is False
    assert "exists" in body["error"].lower() or "label" in body["error"].lower()


def test_other_checkpoint_errors_still_500(client, monkeypatch):
    """Errors that are NOT UNIQUE collisions must keep their 500 status
    so we don't mask real bugs as conflicts."""
    from frontend.blueprints import time_wizard_bp as bp_mod

    def _raise_other(*a, **kw):
        raise Exception("disk on fire")

    monkeypatch.setattr(
        bp_mod.time_wizard, "create_workflow_checkpoint", _raise_other,
        raising=True,
    )
    r = client.post(
        "/api/time/checkpoints",
        json={"label": "lbl", "agent": "t", "description": ""},
    )
    assert r.status_code == 500


# ── S-F96EC5B78A: cross-endpoint regression sweep ───────────────────────────

@pytest.mark.parametrize("path,bodies", [
    ("/api/node/register", [
        {"name": [1, 2, 3], "url": "https://x", "api_key": "k"},
        {"name": {"x": 1}, "url": "https://x", "api_key": "k"},
    ]),
    ("/api/node/discover", [
        {"url": [1], "api_key": "k"},
        {"url": {"u": "https://x"}, "api_key": "k"},
    ]),
    ("/api/library/ingest", [
        {"content": [1]},
        {"content": {"x": "y"}},
    ]),
])
def test_cross_endpoint_no_500_from_type_confusion(client, path, bodies):
    for body in bodies:
        r = client.post(path, json=body)
        assert r.status_code < 500, (
            f"{path} payload {body!r} → {r.status_code} {r.data[:200]!r}"
        )
