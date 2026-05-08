"""V8 Phase-5 MED guards for globally-accessible affordances.

Covers:
* S-55A2D6F9E5 — Spotlight shortcut is wired at document level so it works
   from every window (Ctrl/Meta + Space).
* S-3211C7FD64 — Universal `?` help button exists on every managed window
   header AND on every home tile (hover).
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INIT_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'init.js'
WINDOW_MGR_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'window-manager.js'


def test_spotlight_shortcut_is_wired_globally():
    src = INIT_JS.read_text()
    assert "(e.ctrlKey || e.metaKey) && e.key === ' '" in src
    assert "openSpotlight()" in src


def test_every_window_header_has_help_button():
    src = WINDOW_MGR_JS.read_text()
    assert "openWindowHelp('${id}')" in src or 'openWindowHelp(`${id}`)' in src
    assert 'class="window-btn"' in src


def test_every_home_tile_gets_hover_help_button():
    src = INIT_JS.read_text()
    assert "document.querySelectorAll('.home-card[data-win-id]')" in src
    assert 'home-card-help-btn' in src
    assert "openWindowHelp(winId)" in src
