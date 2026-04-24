"""V7C-R7 — Settings and Trace as normal windows.

Project: P-E9BAE4159F
Step:    S-A95C775790

Settings was historically a fixed modal (`#settings-box`). It is now openable
as a draggable/resizable free window via `openSettingsWindow()` (V7C-A02).
Trace has its own home card and view-trace template and launches via
`openWindow('trace',...)` like any other normal window.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
THEME_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'theme.js'
MODALS_CSS = ROOT / 'frontend' / 'static' / 'css' / 'modals.css'


# R1 TRACE TILE — home card launches Trace via openWindow framework
def test_r1_trace_is_a_normal_window():
    tpl = TEMPLATE.read_text()
    assert 'data-win-id="trace"' in tpl
    assert 'data-win-template="view-trace"' in tpl
    assert '<template id="view-trace">' in tpl


# R2 SETTINGS — opens via winManager openWindow, not fixed modal
def test_r2_settings_has_window_open_path():
    src = THEME_JS.read_text()
    assert "function toggleSettings(" in src
    assert "function loadSettingsWindowData(" in src
    # Uses the generic window manager (the same pipe every normal window uses).
    assert "openWindow(FRIDAYS_SETTINGS_WINDOW_ID" in src


# R3 SETTINGS-BOX — window host placeholder exists so it can be re-parented
def test_r3_settings_box_has_window_host():
    src = THEME_JS.read_text()
    # When the window opens, the host element receives settings-box.
    assert "settings-window-host" in src
    # And it properly restores to modal on close (no memory leak / orphan).
    assert "beforeClose = _restoreSettingsBoxToModal" in src


# R4 NO-WIN FALLBACK — if winManager missing, reverts to modal (graceful)
def test_r4_graceful_no_winmanager_fallback():
    src = THEME_JS.read_text()
    assert "!winManager || typeof openWindow !== 'function'" in src
    assert "modal?.classList.toggle('open')" in src


# R5 TRACE + TRACED DISTINCT — two templates, one for live badge one for history
def test_r5_trace_and_traced_both_windows():
    tpl = TEMPLATE.read_text()
    assert '<template id="view-trace">' in tpl
    assert '<template id="view-traced">' in tpl


# R6 OPEN PATH — trace bus wires click → open Traced window
def test_r6_trace_bus_opens_traced():
    bus = (ROOT / 'frontend' / 'static' / 'js' / 'core' / 'trace-bus.js').read_text()
    assert "open Traced window" in bus


# R7 REGRESSION — no inline "modal-only" lock on settings-box
def test_r7_no_forced_modal_lock():
    css = MODALS_CSS.read_text()
    # If a rule forced `#settings-box { position: fixed !important; }` with no
    # .free escape it would permanently trap Settings as a modal. Guard against it.
    # Look for settings-box fixed+important WITHOUT a .free exception.
    bad = "#settings-box{position:fixed!important"
    assert bad.replace(' ', '') not in css.replace(' ', '')
