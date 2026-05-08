from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'theme.js'
APP_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'app.js'
WINDOW_MANAGER_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'window-manager.js'
TERMINAL_BASE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'


def test_settings_toggle_uses_managed_window_bridge():
    src = THEME_JS.read_text()
    assert "const FRIDAYS_SETTINGS_WINDOW_ID = 'settings';" in src
    assert "openWindow(FRIDAYS_SETTINGS_WINDOW_ID, 'Settings', FRIDAYS_SETTINGS_WINDOW_TEMPLATE_ID" in src
    assert "winManager.close(FRIDAYS_SETTINGS_WINDOW_ID);" in src
    assert "host.replaceWith(box);" in src


def test_settings_window_loader_is_registered():
    src = APP_JS.read_text()
    assert "else if (id === 'settings') loadSettingsWindowData && loadSettingsWindowData(win);" in src


def test_window_manager_preserves_settings_dom_on_close():
    src = WINDOW_MANAGER_JS.read_text()
    assert "if (typeof win.beforeClose === 'function') {" in src
    assert "win.beforeClose();" in src


def test_settings_theme_controls_use_range_sliders():
    """V7C-A03 reconciliation (2026-04-24): the earlier "migrated off sliders"
    framing was explicitly reversed by the user in V8C Wave 1 — "bring back
    the sliders... this is now V9 + V7 + V7C correction of corrections".

    Invariant is now: the six atmosphere controls are <input type="range"> for
    live-preview UX parity with the pre-refactor baseline. Font-size stays a
    <select> (explicit user preference, precision over range). This test locks
    that shape so the regression cannot silently return.
    """
    src = TERMINAL_BASE.read_text()
    for control_id in (
        'atmosphere-slider',
        'accent-slider',
        'hue-slider',
        'contrast-slider',
        'opacity-slider',
        'glow-slider',
    ):
        # Attribute order in the template is `id="…" type="range"`. Assert
        # on both fragments independently rather than coupling to authoring
        # order — keeps the invariant while tolerating harmless reformats.
        tag_open = f'<input id="{control_id}"'
        assert tag_open in src, f'{control_id}: expected <input id="{control_id}" ...>'
        tag_idx = src.index(tag_open)
        tag_end = src.index('>', tag_idx)
        tag = src[tag_idx:tag_end + 1]
        assert 'type="range"' in tag, (
            f'{control_id} must be type="range" — sliders were restored in '
            f'V8C Wave 1 per explicit user instruction. Got: {tag!r}'
        )
        # Guard: no stray <select id="atmosphere-slider"> reintroduction.
        assert f'<select id="{control_id}"' not in src, (
            f'{control_id} must not be a <select> — that was the V7 regression '
            f'the user flagged.'
        )
    # Font-size deliberately stays a <select> for precision.
    assert '<select id="theme-font-size-select"' in src, (
        'theme-font-size-select must remain a <select> — precision UX, user '
        'preference on record in /memories/memory_ten.md.'
    )
