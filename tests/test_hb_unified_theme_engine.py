"""Tests for the unified single-engine Theme + Atmosphere system (no more two-layer conflict)."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_settings_atmosphere_window_exposes_hummingbird_and_presets():
    html = (ROOT / 'frontend/templates/terminal_base.html').read_text(encoding='utf-8')
    assert 'id="settings-theme-presets"' in html
    assert "setNamedTheme('hummingbird')" in html
    # Both Settings modal and taskbar picker share the exact same setNamedTheme('hummingbird') call
    assert html.count("setNamedTheme('hummingbird')") >= 2


def test_theme_js_clears_inline_atmosphere_vars_for_named_themes_and_valid_syntax():
    js_path = ROOT / 'frontend/static/js/core/theme.js'
    js = js_path.read_text(encoding='utf-8')
    assert 'function _clearInlineAtmosphereVars' in js
    assert '_clearInlineAtmosphereVars(document.documentElement)' in js
    assert '_clearInlineAtmosphereVars(win.el)' in js
    assert '#settings-theme-presets .theme-picker-item[data-theme]' in js
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
