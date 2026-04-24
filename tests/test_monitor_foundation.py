from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'monitor.js'


def test_monitor_runtime_view_keeps_health_surfaces():
    src = MONITOR_JS.read_text()
    assert 'id="monitor-alm-status"' in src
    assert 'id="monitor-services"' in src
    assert 'id="monitor-activity"' in src
    assert 'ALM Governance' in src
    assert 'Service Health' in src
    assert 'System Activity' in src


def test_monitor_runtime_view_refreshes_health_sources():
    src = MONITOR_JS.read_text()
    assert "fetch('/api/services')" in src
    assert "fetch('/api/activity')" in src
    assert '_renderMonitorServices(win);' in src
    assert '_renderMonitorActivity(win);' in src
