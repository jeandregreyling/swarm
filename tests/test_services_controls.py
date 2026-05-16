import sys
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))


def test_services_status_groups_prod_dev_uat_and_runtime(monkeypatch):
    from frontend.blueprints import exec_bp

    monkeypatch.setattr(exec_bp, "_systemctl_is_active", lambda unit: (unit == "swarm-terminal.service", "active" if unit == "swarm-terminal.service" else "inactive"))
    monkeypatch.setattr(exec_bp, "_systemctl_is_enabled", lambda unit: "enabled")
    monkeypatch.setattr(exec_bp, "_ollama_runner_rows", lambda: [{"pid": 123, "cmd": "ollama runner --model blob"}])

    app = Flask(__name__)
    with app.app_context():
        data = exec_bp.api_services_status().get_json()

    envs = {item["env"] for item in data}
    ids = {item["id"] for item in data}
    assert {"PROD", "DEV", "UAT", "SHARED", "RUNTIME"} <= envs
    assert "swarm-terminal.service" in ids
    assert "swarm-terminal-prod" not in ids
    assert any(item["id"] == "ollama-runners" and item["can_kill"] for item in data)


def test_service_restart_rejects_unregistered_services():
    from frontend.blueprints import exec_bp

    app = Flask(__name__)
    with app.test_request_context("/api/services/not-real/restart", method="POST", json={}):
        response, status = exec_bp.api_service_restart("not-real")

    assert status == 400
    assert response.get_json()["ok"] is False


def test_service_hard_restart_uses_kill_then_start(monkeypatch):
    from frontend.blueprints import exec_bp

    calls = []
    monkeypatch.setattr(exec_bp, "_run_systemctl", lambda args, timeout=20: calls.append(tuple(args)) or (True, "ok"))
    monkeypatch.setattr(exec_bp, "_service_payload", lambda svc: {**svc, "active": True, "status": "active"})
    monkeypatch.setattr(exec_bp, "_log_watchdog_service_action", lambda *args, **kwargs: None)

    app = Flask(__name__)
    with app.test_request_context("/api/services/swarm-terminal.service/restart", method="POST", json={"mode": "hard"}):
        data = exec_bp.api_service_restart("swarm-terminal.service").get_json()

    assert data["ok"] is True
    assert calls == [
        ("kill", "-s", "SIGKILL", "swarm-terminal.service"),
        ("start", "swarm-terminal.service"),
    ]
