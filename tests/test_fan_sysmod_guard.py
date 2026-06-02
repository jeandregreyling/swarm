from core import fan_controller
from frontend.blueprints import sysmod


def test_fan_summary_warns_when_boost_pwm_is_reverted(monkeypatch):
    monkeypatch.setattr(fan_controller.os.path, "exists", lambda path: True)
    monkeypatch.setattr(fan_controller, "read_temps", lambda: [])

    def fake_query(cmd, payload=None):
        assert cmd == "status"
        return {
            "ok": True,
            "mode": "boost",
            "pwm_readback": [{"path": "/sys/class/hwmon/hwmon3/pwm1", "value": 128}],
            "turbo_disabled": True,
            "max_perf_pct": 40,
            "watchdog_alive": True,
        }

    monkeypatch.setattr(fan_controller, "_query_helper", fake_query)

    summary = fan_controller.summary()

    assert summary["warnings"][0]["code"] == "pwm_firmware_reverted"
    assert summary["helper_state"]["warnings"][0]["pwm_readback"] == [128]


def test_sysmod_fan_helper_install_cmd_includes_executable():
    helper = next(h for h in sysmod._HELPERS if h["id"] == "swarm-fanctl")

    state = sysmod._systemctl_state(helper)

    assert "ops/swarm-fanctl.py" in state["install_cmd"]
    assert "/usr/local/bin/swarm-fanctl" in state["install_cmd"]
    assert "swarm-fanctl.service" in state["install_cmd"]
    assert "binary_installed" in state
    assert "binary_current" in state
