"""V8 home/taskbar/orb/tile regression guards.

Covers the [SMALL] V8 backlog items whose behaviour is already landed in
the shipped code paths; these tests pin the contract so future refactors
can't silently regress them.

Items:
* S-10BD6481C6 — World clocks restored to header (`#world-clocks` present).
* S-C4A0EF382F — Ctrl+Space tip sits inside `#home-controls`.
* S-78C5F23813 — "+" Add-new tile lives inside the Quick Access heading.
* S-94180436C6 — Taskbar launchers have an enlarged style + SVG fallback.
* S-DEFC25E13C — Taskbar derives launchers from tile metadata at runtime.
* S-A5C3BC3F85 — Orb double-click clears custom home (rebase to natural).
* S-184AD0E656 — Tiles in Quick Access grid are drag-and-drop reorderable.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERMINAL_BASE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
APP_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'app.js'
WINDOW_MGR_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'window-manager.js'
TASKBAR_CSS = ROOT / 'frontend' / 'static' / 'css' / 'taskbar.css'
ORBS_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'orbs.js'


def test_world_clocks_container_present_in_header():
    src = TERMINAL_BASE.read_text()
    assert '<div id="world-clocks">' in src


def test_spotlight_tip_lives_inside_home_controls():
    src = TERMINAL_BASE.read_text()
    # #home-controls opens, then a button#spotlight-tip appears before it closes.
    start = src.index('<div id="home-controls">')
    end = src.index('</div>', src.index('services-dropdown-menu'))
    region = src[start:end]
    assert 'id="spotlight-tip"' in region
    assert 'Ctrl' in region and 'Space' in region


def test_add_new_tile_button_folded_into_quick_access_title():
    src = TERMINAL_BASE.read_text()
    # Button sits inside the #quick-access-title heading.
    title_start = src.index('id="quick-access-title"')
    title_end = src.index('</div>', title_start)
    region = src[title_start:title_end]
    assert 'id="quick-access-add-btn"' in region


def test_taskbar_launcher_has_enlarged_style_and_svg_fallback():
    css = TASKBAR_CSS.read_text()
    assert '.taskbar-launcher-btn' in css
    wm = WINDOW_MGR_JS.read_text()
    # Generic fallback SVG when a window id has no mapped icon.
    assert 'FRIDAYS_WINDOW_ICON_SVGS[key]' in wm
    assert '|| \'<svg' in wm  # explicit fallback OR path


def test_taskbar_derives_launchers_from_tile_metadata():
    src = APP_JS.read_text()
    assert "document.getElementById('taskbar-launchers')" in src
    assert "document.querySelectorAll('#quick-cards .home-card[data-win-id]')" in src
    assert 'fridaysWindowIconMarkup(winId)' in src


def test_orb_double_click_rebases_to_natural_home():
    src = ORBS_JS.read_text()
    # Double-click clears custom home so the orb returns to its natural roost.
    assert 'customHomeX' in src and 'customHomeY' in src
    assert 'if (hit.customHomeX != null || hit.customHomeY != null)' in src
    assert 'hit.customHomeX = null' in src
    assert 'hit.customHomeY = null' in src


def test_quick_access_tiles_support_drag_and_drop_reorder():
    src = APP_JS.read_text()
    # Drag session: pointerdown on .home-card → _startDrag → drag-placeholder.
    assert "grid.querySelectorAll('.home-card').forEach(c => c.classList.add('drag-ready'));" in src
    assert "grid.addEventListener('pointerdown'" in src
    assert 'drag-placeholder' in src
    assert 'insertBefore(placeholder' in src
