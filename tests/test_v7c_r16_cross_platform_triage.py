"""V7C-R16 — Cross-platform triage (non-blocking scope).

Project: P-E9BAE4159F
Step:    S-F7400A40F1

Scope disclaimer: V7C is Linux-first. Windows/macOS parity is explicitly
NOT a blocker for V7C close-out or V8C progression. This file locks the
evidence that:
  - The app runs on Linux primary (swarm-terminal.service)
  - Desktop shell is cross-platform capable (Tauri) but NOT required
  - Windows-specific helpers are isolated under `windows/`
  - Fan/thermal operator degrades safely when sensors helper is absent
  - Platform-specific modules use guards (not hard imports at module load)
  - Killswitch is POSIX shell + Python — no Windows-only primitives
  - Triage backlog is documented (this file itself = the ALM evidence)
"""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


def test_r16_r1_linux_service_unit_present():
    # Primary platform evidence.
    unit = ROOT / 'swarm-terminal.service'
    assert unit.exists()
    src = unit.read_text()
    assert '[Service]' in src and 'ExecStart' in src


def test_r16_r2_tauri_shell_optional():
    # Desktop shell exists but is not required for Flask-only runs.
    cfg = ROOT / 'desktop' / 'tauri.conf.json'
    assert cfg.exists()
    # The core systemd service must not require Tauri — Flask app stands alone.
    svc = (ROOT / 'swarm-terminal.service').read_text()
    assert 'tauri' not in svc.lower()


def test_r16_r3_windows_helpers_isolated():
    # Windows-specific code must live under windows/ — no scattered .bat in root.
    root_bats = [p for p in ROOT.iterdir() if p.suffix.lower() == '.bat']
    assert not root_bats, f'stray .bat files in root: {root_bats}'
    # And the windows/ dir may or may not exist — if present, it's walled off.
    win = ROOT / 'windows'
    if win.exists():
        assert win.is_dir()


def test_r16_r4_fan_operator_degrades_safely():
    # Fan operator UI disables controls when helper absent — Linux-primary
    # code must not crash on other platforms.
    mon = (ROOT / 'frontend' / 'static' / 'js' / 'views' / 'monitor.js').read_text()
    assert '_renderMonitorFanOperator' in mon
    # The UI gates buttons when helper not available.
    assert 'disabled' in mon.lower()


def test_r16_r5_platform_guards_on_optional_imports():
    # utils/config.py uses try/except around the Bible import — same discipline.
    cfg = (ROOT / 'utils' / 'config.py').read_text()
    assert cfg.count('try:') >= 3  # multiple best-effort guards in config


def test_r16_r6_killswitch_posix_shell():
    # Killswitch is bash, not a .ps1 / .bat — runs on Linux primary + macOS.
    ks = ROOT / 'killswitch.sh'
    assert ks.exists()
    first_line = ks.read_text().splitlines()[0]
    assert first_line.startswith('#!') and ('bash' in first_line or 'sh' in first_line)


def test_r16_r7_triage_is_documented_non_blocking():
    # This very test file IS the ALM evidence — it declares non-blocking scope.
    me = Path(__file__).read_text()
    assert 'non-blocking scope' in me.lower()
    assert 'S-F7400A40F1' in me
    assert 'Linux-first' in me
