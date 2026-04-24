"""V7C-R8 — Monitor / health / fan operator path.

Project: P-E9BAE4159F
Step:    S-C0E8681F85

Locks the Monitor window's health & fan-operator plumbing:
- /api/monitor polled (cached 5s server-side) with 20s client cadence
- /api/services renders Service Health panel
- /api/activity renders System Activity panel
- /api/monitor ALM panel refreshed
- /api/fan/status + /api/fan/mode backend endpoints exist (A05 wires UI)
- Fan/thermal backend separated from hot refresh path.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MON = (ROOT / 'frontend' / 'static' / 'js' / 'views' / 'monitor.js').read_text()
FAN = (ROOT / 'frontend' / 'blueprints' / 'fan.py').read_text()


# R1 MONITOR ENDPOINT — the canonical data pull
def test_r1_monitor_polls_api_monitor():
    assert "fetch('/api/monitor')" in MON
    # Cadence comment present and explicit.
    assert "20000" in MON


# R2 SERVICE HEALTH — wired to /api/services
def test_r2_service_health_panel():
    assert "fetch('/api/services')" in MON
    assert "'Service Health'" in MON or "Service Health" in MON
    assert "monitor-services" in MON


# R3 ACTIVITY — wired to /api/activity
def test_r3_activity_panel():
    assert "fetch('/api/activity')" in MON
    assert "mn-activity-body" in MON


# R4 ALM GOVERNANCE — rendered and refreshed on slow cadence
def test_r4_alm_governance_panel():
    assert "renderMonitorAlm" in MON
    assert "monitor-alm-status" in MON
    # Slow cadence (30s) to avoid hammering governance.
    assert "30000" in MON


# R5 FAN BACKEND — routes exist (A05 is the UI; R8 requires the path)
def test_r5_fan_backend_routes():
    assert "/api/fan/status" in FAN
    assert "/api/fan/mode" in FAN
    assert "methods=['GET']" in FAN
    assert "methods=['POST']" in FAN


# R6 NO FAN CALL IN MONITOR HOT LOOP — fan control must NOT be pounded every tick
def test_r6_fan_not_in_monitor_hot_loop():
    # R8 contract: fan operator lives on its own path, not inside monitor tick.
    start = MON.index("const refreshMonitor = ()")
    end   = MON.index("win._monitorRefreshFn = refreshMonitor")
    hot = MON[start:end]
    assert "/api/fan/status" not in hot
    assert "/api/fan/mode" not in hot


# R7 CLEANUP — timers cleared when monitor window closes (leak guard)
def test_r7_monitor_timer_cleanup():
    assert "clearInterval(win._monitorTimer)" in MON
    assert "clearInterval(win._monitorAlmTimer)" in MON
    assert "winManager.windows.has(win.id)" in MON
