import sys
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))


def _fake_unit_state(installed_units):
    def _state(unit, scope="system"):
        if unit not in installed_units:
            return {"LoadState": "not-found", "ActiveState": "inactive", "SubState": "dead", "UnitFileState": ""}
        return {"LoadState": "loaded", "ActiveState": "active", "SubState": "running", "UnitFileState": "enabled"}
    return _state


def test_services_status_groups_prod_dev_uat_and_runtime(monkeypatch):
    from frontend.blueprints import exec_bp

    monkeypatch.setattr(exec_bp, "_unit_state", _fake_unit_state({"swarm-terminal.service", "swarm-vortex-backup.timer"}))
    monkeypatch.setattr(exec_bp, "_ollama_runner_rows", lambda: [{"pid": 123, "cmd": "ollama runner --model blob"}])
    monkeypatch.setattr(exec_bp, "_llama_resident_rows", lambda: [{"model": "gemma3:latest", "pid": 9, "port": 18979, "gpu": True, "ram_gb": 1.0, "idle_seconds": 5}])

    app = Flask(__name__)
    with app.app_context():
        data = exec_bp.api_services_status().get_json()

    by_id = {item["id"]: item for item in data}
    assert {"PROD", "DEV", "UAT", "SHARED", "RUNTIME"} <= {item["env"] for item in data}
    assert by_id["swarm-terminal.service"]["installed"] and by_id["swarm-terminal.service"]["active"]
    assert "swarm-terminal-prod" not in by_id
    monitor = by_id["swarm-monitor.service"]
    assert monitor["installed"] is False and monitor["status"] == "not installed"
    assert monitor["can_restart"] is False and monitor["can_hard_restart"] is False
    assert by_id["swarm-vortex-backup.timer"]["scope"] == "user"
    assert by_id["llama-server"]["models"][0]["model"] == "gemma3:latest"
    assert by_id["ollama-runners"]["can_kill"]


def test_service_restart_rejects_unregistered_services():
    from frontend.blueprints import exec_bp

    app = Flask(__name__)
    with app.test_request_context("/api/services/not-real/restart", method="POST", json={}):
        response, status = exec_bp.api_service_restart("not-real")

    assert status == 400
    assert response.get_json()["ok"] is False


def _restart(exec_bp, monkeypatch, unit, mode, installed=True):
    calls = []
    monkeypatch.setattr(exec_bp, "_run_systemctl",
                        lambda args, timeout=20, scope="system": calls.append((scope,) + tuple(args)) or (True, "ok"))
    monkeypatch.setattr(exec_bp, "_unit_state", _fake_unit_state({unit} if installed else set()))
    monkeypatch.setattr(exec_bp, "_log_watchdog_service_action", lambda *args, **kwargs: None)
    import database
    monkeypatch.setattr(database, "log_activity", lambda *args, **kwargs: None)
    app = Flask(__name__)
    with app.test_request_context(f"/api/services/{unit}/restart", method="POST", json={"mode": mode}):
        result = exec_bp.api_service_restart(unit)
    response, status = result if isinstance(result, tuple) else (result, 200)
    return response.get_json(), status, calls


def test_service_hard_restart_uses_kill_then_start(monkeypatch):
    from frontend.blueprints import exec_bp

    data, _, calls = _restart(exec_bp, monkeypatch, "ollama.service", "hard")
    assert data["ok"] is True
    assert calls == [
        ("system", "kill", "-s", "SIGKILL", "ollama.service"),
        ("system", "start", "ollama.service"),
    ]


def test_self_restart_is_queued_without_blocking(monkeypatch):
    from frontend.blueprints import exec_bp

    for mode in ("restart", "hard"):
        data, _, calls = _restart(exec_bp, monkeypatch, "swarm-terminal.service", mode)
        assert data["ok"] is True
        assert calls == [("system", "restart", "--no-block", "swarm-terminal.service")]


def test_user_units_restart_without_sudo(monkeypatch):
    from frontend.blueprints import exec_bp

    data, _, calls = _restart(exec_bp, monkeypatch, "swarm-vortex-backup.timer", "restart")
    assert data["ok"] is True
    assert calls == [("user", "restart", "swarm-vortex-backup.timer")]


def test_restart_refuses_units_not_installed(monkeypatch):
    from frontend.blueprints import exec_bp

    data, status, calls = _restart(exec_bp, monkeypatch, "swarm-monitor.service", "restart", installed=False)
    assert status == 404 and data["ok"] is False and calls == []


def test_system_units_use_noninteractive_sudo_with_hint(monkeypatch):
    import subprocess
    from frontend.blueprints import exec_bp

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 1, "", "sudo: a password is required\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, output = exec_bp._run_systemctl(["restart", "ollama.service"])
    assert ok is False
    assert seen["cmd"][:3] == ["sudo", "-n", "/usr/bin/systemctl"]
    assert "install_service_sudoers.sh" in output


def test_agents_can_read_local_service_status_but_nothing_else():
    from fridays.shell_agent import _match_whitelist

    assert _match_whitelist("curl -s http://127.0.0.1:5050/api/services")[0] == 0
    assert _match_whitelist("curl -s http://127.0.0.1:5050/api/services; rm -rf x") is None
    assert _match_whitelist("curl -s https://example.com")[0] == 4
