"""V8 medium-surface regression guards.

Covers Phase-5 MED + [MEDIUM] items whose behaviour is already landed:

* S-B36E412429 — Monitor exposes a Service Health panel.
* S-2532C170F0 — Studio defaults to the Projects tab.
* S-DDC3BE108D — Settings tile opens via the managed window bridge.
* S-6994AB45C1 — Trace tile is a registered managed window template.
* S-99E6F8B377 — Owner identity is normalised separately from generic
   swarm mailbox surfaces (via `login_bp._ensure_owner` + duplicate-email
   guard in `auth_edit_user`).
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'monitor.js'
STUDIO_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'studio.js'
TERMINAL_BASE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
WINDOW_MGR_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'window-manager.js'
THEME_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'theme.js'
LOGIN_BP = ROOT / 'frontend' / 'blueprints' / 'login_bp.py'


def test_monitor_shows_service_health_panel():
    src = MONITOR_JS.read_text()
    # Panel renders a labelled Service Health block when data arrives and
    # when it is empty — both code paths must exist.
    assert "<div style=\"font-weight:600;margin-bottom:6px;\">Service Health</div>" in src


def test_studio_defaults_to_projects_tab():
    src = STUDIO_JS.read_text()
    assert (
        "localStorage.getItem('studio_last_tab') || 'projects'" in src
        or "window._studioTab = window._studioTab || 'projects';" in src
    )
    assert "window._studioTab = 'projects'" in src


def test_trace_tile_registered_as_managed_window_template():
    src = TERMINAL_BASE.read_text()
    assert 'data-win-id="trace"' in src
    assert 'data-win-template="view-trace"' in src
    # Template block exists.
    assert '<template id="view-trace">' in src
    # Taskbar icon map carries a trace entry.
    wm = WINDOW_MGR_JS.read_text()
    assert "trace: '<svg" in wm


def test_settings_tile_uses_managed_window_bridge():
    src = THEME_JS.read_text()
    assert "const FRIDAYS_SETTINGS_WINDOW_ID = 'settings';" in src
    assert "openWindow(FRIDAYS_SETTINGS_WINDOW_ID, 'Settings'" in src


def test_owner_identity_is_separated_from_generic_mailbox_surfaces():
    src = LOGIN_BP.read_text()
    # _ensure_owner normalises the owner row independently of any other
    # user rows; duplicate-email assignment is rejected in auth_edit_user.
    assert 'def _ensure_owner' in src
    assert 'GHOST_EMAIL' in src
    assert 'duplicate' in src.lower() or 'already' in src.lower()
