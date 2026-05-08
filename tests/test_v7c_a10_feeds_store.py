"""V7C-A10 refinement — real feeds subscription store + RSS fetch.

Closes the deferred bullets from the A10 partial. Replaces localStorage-only
persistence with ``core.feeds`` (SQLite) and exposes an HTTP blueprint.
Third-party OAuth connectors remain out of scope (honestly recorded as
``pending``), but the swarm can now *see* what the user is subscribed to.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from flask import Flask


@pytest.fixture()
def db_env(monkeypatch, tmp_path):
    """Point the swarm DB at an isolated sqlite file for each test."""
    db_path = tmp_path / "swarm_feeds_test.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    # utils.db._connection caches the path; clear its module-level state.
    import importlib
    import utils.db._connection as _dbc
    importlib.reload(_dbc)
    yield str(db_path)
    # Restore the module's cached DB path to whatever the real env says
    # now that monkeypatch has undone our setenv. Without this, later tests
    # in the same pytest session see the tmp path and can't find real data.
    importlib.reload(_dbc)


@pytest.fixture()
def feeds_client(db_env):
    # Isolated Flask app wired to just the feeds blueprint.
    from frontend.blueprints.feeds_bp import feeds_bp
    app = Flask(__name__)
    app.register_blueprint(feeds_bp)
    return app.test_client()


def test_a10_schema_bootstraps(db_env):
    from core import feeds
    feeds.ensure_schema()
    assert feeds.list_subscriptions() == []


def test_a10_add_and_list(db_env):
    from core import feeds
    sid = feeds.add_subscription("rss", "https://example.com/rss.xml",
                                  title="Example RSS")
    assert sid.startswith("F-")
    items = feeds.list_subscriptions()
    assert len(items) == 1
    assert items[0]["url"] == "https://example.com/rss.xml"
    assert items[0]["status"] == "pending"
    assert items[0]["enabled"] is True


def test_a10_rejects_unknown_kind(db_env):
    from core import feeds
    with pytest.raises(ValueError):
        feeds.add_subscription("carrier-pigeon", "https://x/y")


def test_a10_http_crud_roundtrip(feeds_client):
    # Create
    r = feeds_client.post("/api/feeds/subscriptions",
                          json={"kind": "rss", "url": "https://e.com/r.xml"})
    assert r.status_code == 200, r.get_json()
    sid = r.get_json()["sub_id"]
    # List
    r = feeds_client.get("/api/feeds/subscriptions")
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert any(i["sub_id"] == sid for i in items)
    # Patch (disable)
    r = feeds_client.patch(f"/api/feeds/subscriptions/{sid}",
                           json={"enabled": False})
    assert r.status_code == 200
    items = feeds_client.get("/api/feeds/subscriptions").get_json()["items"]
    assert next(i for i in items if i["sub_id"] == sid)["enabled"] is False
    # Delete
    r = feeds_client.delete(f"/api/feeds/subscriptions/{sid}")
    assert r.status_code == 200
    items = feeds_client.get("/api/feeds/subscriptions").get_json()["items"]
    assert not any(i["sub_id"] == sid for i in items)


def test_a10_oauth_connector_marked_pending(feeds_client):
    r = feeds_client.post("/api/feeds/subscriptions",
                          json={"kind": "hn", "url": "https://news.ycombinator.com"})
    sid = r.get_json()["sub_id"]
    # Poll — HN has no connector, must return ok=false but 200 (not 5xx),
    # and persist status='pending' with an explanation.
    r = feeds_client.post(f"/api/feeds/subscriptions/{sid}/poll")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is False
    assert "not implemented" in (body.get("error") or "").lower()
    items = feeds_client.get("/api/feeds/subscriptions").get_json()["items"]
    hn = next(i for i in items if i["sub_id"] == sid)
    assert hn["status"] == "pending"
    assert hn["last_error"] and "not implemented" in hn["last_error"].lower()


def test_a10_rss_parser_on_static_fixture(db_env, monkeypatch):
    # Build a tiny RSS XML in-memory and short-circuit urlopen to return it.
    from core import feeds
    rss = (b"<?xml version='1.0'?>"
           b"<rss><channel>"
           b"<item><title>One</title><link>http://x/1</link>"
           b"<description>D1</description><pubDate>2026-04-24</pubDate></item>"
           b"<item><title>Two</title><link>http://x/2</link>"
           b"<description>D2</description><pubDate>2026-04-24</pubDate></item>"
           b"</channel></rss>")

    class _Resp:
        def __init__(self, body): self._b = body
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(feeds, "urlopen", lambda *a, **kw: _Resp(rss))
    items = feeds.fetch_rss("http://ignored/feed.xml")
    assert len(items) == 2
    assert items[0]["title"] == "One"
    assert items[1]["link"] == "http://x/2"


def test_a10_poll_success_updates_status(db_env, monkeypatch):
    from core import feeds
    sid = feeds.add_subscription("rss", "http://any/feed.xml")
    monkeypatch.setattr(feeds, "fetch_rss",
                        lambda *a, **kw: [{"title": "t", "link": "l",
                                            "summary": "", "published": ""}])
    rep = feeds.poll_once(sid)
    assert rep["ok"] is True
    assert rep["count"] == 1
    items = feeds.list_subscriptions()
    assert items[0]["status"] == "connected"
    assert items[0]["last_poll"] is not None
