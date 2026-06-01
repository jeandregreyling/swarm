from __future__ import annotations

from flask import Flask


def test_vpn_status_degrades_when_tailscale_unavailable(monkeypatch):
    from frontend.blueprints import vpn_bp as vpn_mod

    monkeypatch.setattr(vpn_mod, "_tailscale_status", lambda: {"error": "tailscale binary not found"})

    app = Flask(__name__)
    app.register_blueprint(vpn_mod.vpn_bp)
    client = app.test_client()

    resp = client.get("/api/vpn/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["available"] is False
    assert data["backend_state"] == "unavailable"
    assert data["error_code"] == "VPN_UNAVAILABLE"
    assert data["peer_count"] == 0
    assert data["online_count"] == 0
    assert data["peers"] == []
    assert data["self"] == {}
    assert "tailscale binary not found" in data["error"]
