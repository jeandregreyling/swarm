"""Tests for Open-Tower 8-Fan Cooling (IT8689E pwm1..5 + no Dell CPU throttle) & Fan-First Safe GPU Overclock."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_swarm_fanctl_supports_pwm5_and_does_not_throttle_desktop_cpu(monkeypatch):
    fanctl = _load('ops/swarm-fanctl.py', 'hb_test_fanctl')
    src = (ROOT / 'ops/swarm-fanctl.py').read_text(encoding='utf-8')
    assert "'pwm5'" in src
    # Desktop rig with real pwm1_enable gates must NOT trigger legacy Dell 40% CPU throttle
    monkeypatch.setattr(fanctl, '_pwm_paths', lambda: [('/sys/class/hwmon/hwmon4/pwm1', '/sys/class/hwmon/hwmon4/pwm1_enable')])
    assert fanctl._needs_dell_cpu_throttle() is False


def test_gpu_profile_spools_gpu_fans_before_overclock_and_restores_auto_on_reset():
    src = (ROOT / 'scripts/hb_gpu_profile.py').read_text(encoding='utf-8')
    assert "write(pwm_en, '1')" in src
    assert "p.get('fan_pwm', 225)" in src
    assert "write(pwm_en, '2')" in src
    assert "'fan_pwm'" in src
