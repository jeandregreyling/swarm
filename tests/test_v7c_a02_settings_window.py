"""V7C-A02 — Settings still a fixed modal, not a normal window.

Project: P-E9BAE4159F
Step:    S-75D2D60EBE
Case:    C-E9FFD6B8A1
Script:  pytest:settings-window-bridge (council-of-7 expansion)

Before this test existed the window-manager bridge wiring was present but
never fully locked. A03 (sliders-off) conflicted with this area and was
reconciled simultaneously in tests/test_settings_window_bridge.py.

Intent: when the user clicks the Settings button, Settings must appear as a
first-class draggable/closable window via winManager — not as a centred modal
overlay. The old #settings-modal overlay is retained only as a fallback for
code paths where winManager is unavailable (e.g. pre-boot).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'theme.js'
APP_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'app.js'
WINDOW_MANAGER_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'window-manager.js'
TEMPLATE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
INIT_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'init.js'


# ── Reviewer 1: FUNCTIONAL — toggleSettings prefers winManager path ─────────
def test_r1_toggle_prefers_managed_window():
    src = THEME_JS.read_text()
    # toggleSettings must exist and consult winManager first
    assert "function toggleSettings()" in src
    idx = src.index("function toggleSettings()")
    body = src[idx:idx + 1500]
    assert "winManager?.windows?.get(FRIDAYS_SETTINGS_WINDOW_ID)" in body, (
        "toggleSettings must check winManager for an existing Settings window."
    )
    assert "openWindow(FRIDAYS_SETTINGS_WINDOW_ID" in body, (
        "toggleSettings must open the managed window path, not the overlay."
    )


# ── Reviewer 2: LOADER WIRING — app.js routes id='settings' → loader ────────
def test_r2_app_js_routes_settings_to_loader():
    src = APP_JS.read_text()
    assert (
        "else if (id === 'settings') loadSettingsWindowData && loadSettingsWindowData(win);"
        in src
    ), "app.js openWindow switch must route 'settings' to loadSettingsWindowData."


# ── Reviewer 3: DOM REPARENTING — settings-box moves into window host ──────
def test_r3_settings_box_reparents_into_window_host():
    src = THEME_JS.read_text()
    assert "function loadSettingsWindowData(win)" in src
    idx = src.index("function loadSettingsWindowData(win)")
    body = src[idx:idx + 800]
    assert "host.replaceWith(box);" in body, (
        "loadSettingsWindowData must move the real #settings-box DOM into the "
        "window host — don't render a stale copy."
    )
    # beforeClose must restore the box back into the modal shell so the
    # next-open path (fallback) still has the DOM available.
    assert "win.beforeClose = _restoreSettingsBoxToModal;" in body


# ── Reviewer 4: CLOSE PATH — closeSettings routes through winManager ───────
def test_r4_close_routes_through_window_manager():
    src = THEME_JS.read_text()
    assert "function closeSettings()" in src
    idx = src.index("function closeSettings()")
    body = src[idx:idx + 400]
    assert "winManager.close(FRIDAYS_SETTINGS_WINDOW_ID)" in body
    # Fallback must still handle the pre-window overlay case.
    assert "_restoreSettingsBoxToModal()" in body


# ── Reviewer 5: beforeClose CONTRACT — window-manager honours it ───────────
def test_r5_window_manager_honours_before_close():
    src = WINDOW_MANAGER_JS.read_text()
    assert "if (typeof win.beforeClose === 'function') {" in src, (
        "window-manager must call win.beforeClose() before tearing the window "
        "down — otherwise #settings-box leaks out of its host."
    )
    assert "win.beforeClose();" in src


# ── Reviewer 6: FALLBACK SAFETY — overlay path intact for pre-boot ─────────
def test_r6_modal_overlay_fallback_retained():
    """If winManager is unavailable the code must fall back to the legacy
    overlay path. We don't want the user to end up with a no-op Settings
    button if the window manager is still booting."""
    src = THEME_JS.read_text()
    idx = src.index("function toggleSettings()")
    body = src[idx:idx + 1500]
    assert "!winManager || typeof openWindow !== 'function' || !modal" in body, (
        "toggleSettings must retain the overlay fallback branch."
    )
    assert "modal?.classList.toggle('open');" in body

    tpl = TEMPLATE.read_text()
    assert '<div id="settings-modal">' in tpl
    assert '<div id="settings-box"' in tpl
    # Backdrop click still closes (kept from overlay path).
    assert "settings-modal" in INIT_JS.read_text()


# ── Reviewer 7: NO ACCIDENTAL DIRECT OVERLAY CALLS IN NEW CODE ─────────────
def test_r7_no_direct_settings_modal_classlist_add_in_new_entrypoints():
    """If someone reintroduces `document.getElementById('settings-modal').
    classList.add('open')` anywhere new we will know. The permitted callers
    are toggleSettings/closeSettings/init-backdrop-handler only."""
    import re
    theme = THEME_JS.read_text()
    # All `classList.add('open')` / `.classList.remove('open')` on settings-modal
    # must live inside theme.js (toggleSettings/closeSettings) or init.js
    # (backdrop click handler). Nothing else should touch it.
    for candidate in (APP_JS, WINDOW_MANAGER_JS):
        s = candidate.read_text()
        # Accept references in comments/strings, but not direct DOM calls.
        for line in s.splitlines():
            if "settings-modal" in line and (".classList.add(" in line or ".classList.remove(" in line):
                raise AssertionError(
                    f"Direct #settings-modal open/close from {candidate.name}: {line.strip()}"
                )
    # theme.js may have classList.remove('open') (it's the owner).
    # V8 theme-picker added 2 legitimate close paths (setNamedTheme + outside-click).
    assert theme.count(".classList.remove('open');") <= 6, (
        "theme.js has more direct overlay open/close calls than expected — "
        "audit before approving."
    )
