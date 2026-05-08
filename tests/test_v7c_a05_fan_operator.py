"""V7C-A05 — Fan operator UI.

Project: P-E9BAE4159F
Step:    S-2EF5C4EA56

User-facing fan operator inside Monitor window. Reads /api/fan/status, lets
user pick auto/boost via /api/fan/mode POST. Gated by system-modifications
toggle (off by default). Safe default: buttons disabled when helper is absent.
"""
from pathlib import Path

MON = (Path(__file__).resolve().parents[1] / 'frontend' / 'static' / 'js' / 'views' / 'monitor.js').read_text()


def test_a05_r1_fan_host_in_skeleton():
    assert 'id="monitor-fan-operator"' in MON
    # Hidden by default — revealed only after sysmod gate passes.
    assert 'monitor-fan-operator' in MON and 'display:none' in MON


def test_a05_r2_sysmod_gate():
    # Must check getSysmodEnabled and bail early when disabled.
    assert "getSysmodEnabled" in MON
    assert "!window.getSysmodEnabled()" in MON


def test_a05_r3_status_fetch():
    assert "fetch('/api/fan/status')" in MON


def test_a05_r4_mode_post():
    assert "function monitorFanSetMode(" in MON
    assert "fetch('/api/fan/mode'" in MON
    assert "method: 'POST'" in MON
    assert "JSON.stringify({ mode })" in MON


def test_a05_r5_auto_boost_buttons():
    assert "monitorFanSetMode('auto')" in MON
    assert "monitorFanSetMode('boost')" in MON


def test_a05_r6_helper_absent_disables_buttons():
    # When helper_installed is false → buttons disabled (not deceptively clickable).
    assert "helper_installed" in MON
    assert "installed ? '' : 'disabled'" in MON


def test_a05_r7_wired_into_initial_render():
    # Fan operator must be rendered once when skeleton mounts, not polled.
    assert "_renderMonitorFanOperator(win)" in MON
    # And not inside the 20s hot tick (refreshMonitor body, up to its closing).
    start = MON.index("const refreshMonitor = ()")
    end   = MON.index("win._monitorRefreshFn = refreshMonitor")
    hot = MON[start:end]
    assert "_renderMonitorFanOperator" not in hot
