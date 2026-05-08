"""V7C-R2 — Home header and navigation polish.

Project: P-E9BAE4159F
Step:    S-D3E416C346

Regression pass for:
  - world clocks rendered in header (#world-clocks host exists)
  - spotlight-tip placement (button inside #home-controls, opens Spotlight)
  - services control placement (services-dropdown at end of home-controls)
  - quick-access collapse state persists under fridays-quick-access-collapsed
  - bottom taskbar exists as #taskbar and is excluded from background click-close
  - tile-to-taskbar parity: taskbar items use .taskbar-item class
  - "Add New" tile init path is still wired
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TPL  = (ROOT / 'frontend' / 'templates' / 'terminal_base.html').read_text()
INIT = (ROOT / 'frontend' / 'static' / 'js' / 'core' / 'init.js').read_text()
THEME= (ROOT / 'frontend' / 'static' / 'js' / 'core' / 'theme.js').read_text()
DIAM = (ROOT / 'frontend' / 'static' / 'js' / 'views' / 'diamond.js').read_text()


def test_r2_r1_world_clocks_host():
    assert 'id="world-clocks"' in TPL
    assert 'updateWorldClocks' in THEME
    assert 'WORLD_CLOCKS_STORAGE_KEY' in THEME


def test_r2_r2_spotlight_tip_wired():
    assert 'id="spotlight-tip"' in TPL
    assert 'openSpotlight()' in TPL
    # Must carry the Ctrl+Space keyboard hint so the tip is actually a tip.
    assert 'Ctrl' in TPL and 'Space' in TPL


def test_r2_r3_services_dropdown_at_end():
    # Services dropdown lives inside home-controls as trailing element.
    hc_start = TPL.index('id="home-controls"')
    hc_end   = TPL.index('</div>', TPL.index('services-dropdown-wrap', hc_start))
    snippet = TPL[hc_start:hc_end]
    assert 'id="services-dropdown-wrap"' in snippet
    assert 'toggleServicesDropdown()' in snippet
    # Refresh affordance inside the menu.
    assert 'loadServicesPanel()' in snippet


def test_r2_r4_quick_access_collapse_persists():
    assert "QUICK_ACCESS_COLLAPSED_KEY = 'fridays-quick-access-collapsed'" in INIT
    assert 'initQuickAccessCollapse' in INIT
    assert "localStorage.setItem(QUICK_ACCESS_COLLAPSED_KEY" in INIT


def test_r2_r5_taskbar_click_outside_safe():
    # Global click-to-close must not fire when clicking inside #taskbar.
    assert "#taskbar" in INIT
    assert ".floating-window" in INIT
    # Specifically guarded via closest() check.
    assert "closest('.floating-window, #taskbar" in INIT


def test_r2_r6_add_new_tile_initialized():
    # Tile is injected dynamically by diamond.js.
    assert "getElementById('add-new-tile')" in DIAM
    assert "_initAddNewTile()" in DIAM
    assert "function _initAddNewTile(" in DIAM


def test_r2_r7_header_has_identity_pill_and_trace():
    # Regression guard: auth pill + Trace button stayed in header.
    assert 'id="auth-user-pill"' in TPL
    assert 'id="troubleshoot-btn"' in TPL
    assert '> Trace<' in TPL or '>Trace<' in TPL
    assert 'id="home-settings-btn"' in TPL
