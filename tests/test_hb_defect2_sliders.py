"""Tests for Defect 2: Settings sliders (Accent, Hue, Contrast, Glow) live-tune Hummingbird theme."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_named_theme_sliders_live_tune_hummingbird_and_valid_js():
    js_path = ROOT / 'frontend/static/js/core/theme.js'
    js = js_path.read_text(encoding='utf-8')
    assert 'function _applyNamedThemeSliders' in js
    assert 'function _clearNamedSliderOverrides' in js
    assert '_applyNamedThemeSliders(activeNamed)' in js
    assert "document.body.style.setProperty('--accent', tunedAccent)" in js
    assert "document.body.style.setProperty('--hb-aura-a'" in js
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
