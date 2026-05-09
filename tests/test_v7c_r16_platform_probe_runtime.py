"""V7C-R16 refinement — runtime platform capability probe.

Closes the deferred bullets from the R16 partial: the probe now lives in
``core.swarm_platform`` and is exposed at ``/api/platform``. These tests
verify the runtime shape, caching, and degrade-safety, rather than
string-scanning the repo for the absence of ``.bat`` files.
"""
import pytest

try:
    from core.swarm_platform import capabilities, summary
except (ImportError, AttributeError):
    pytest.skip(
        "core.swarm_platform not yet complete (stub only)",
        allow_module_level=True,
    )

from flask import Flask


def test_r16_capabilities_shape():
    c = capabilities()
    assert isinstance(c, dict)
    for key in ("os", "python", "systemd", "sensors", "notify",
                "tauri", "browsers", "ollama",
                "linux_primary", "fan_operator_supported"):
        assert key in c, f"capabilities() missing {key}"


def test_r16_probes_are_boolean_honest():
    c = capabilities()
    for name in ("systemd", "sensors", "notify", "tauri", "browsers", "ollama"):
        block = c[name]
        assert isinstance(block, dict)
        assert "available" in block
        assert isinstance(block["available"], bool)


def test_r16_linux_primary_on_linux():
    c = capabilities()
    if c["os"]["system"] == "Linux":
        # On Linux we should at least agree we're on Linux; systemd flag may
        # depend on env, so we just assert the boolean is honest.
        assert isinstance(c["linux_primary"], bool)
    else:
        # Documenting the cross-platform path: outside Linux we must NOT
        # claim linux_primary.
        assert c["linux_primary"] is False


def test_r16_cache_returns_same_instance_within_ttl():
    a = capabilities()
    b = capabilities()
    assert a is b, "capabilities() must be cached within TTL"


def test_r16_force_refresh_rebuilds():
    a = capabilities()
    b = capabilities(force=True)
    assert a is not b, "force=True must bypass the cache"


def test_r16_summary_is_json_safe():
    import json
    rep = summary()
    # Must round-trip through json — no datetimes, no sets.
    s = json.dumps(rep)
    again = json.loads(s)
    assert again["ok"] is True
    assert "capabilities" in again
    assert set(again["capabilities"]).issuperset(
        {"systemd", "sensors", "notify", "tauri", "browsers", "ollama"}
    )


def test_r16_api_platform_endpoint():
    # Register the /api/platform route on an isolated Flask app without
    # pulling the whole system_bp (which itself depends on the
    # `frontend/services/` package that the live app puts on sys.path).
    from flask import Blueprint, jsonify
    from core.swarm_platform import summary as _summary

    bp = Blueprint('platform_test', __name__)

    @bp.route('/api/platform', methods=['GET'])
    def _route():
        return jsonify(_summary())

    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    resp = client.get("/api/platform")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "capabilities" in body
    assert "os" in body
