"""Tests for Living Hummingbird Liquid-Glass (Melbourne leftmost clock weather + time-of-day aurora)."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_hummingbird_weather_mood_wired_in_theme_js_and_css():
    js_path = ROOT / 'frontend/static/js/core/theme.js'
    js = js_path.read_text(encoding='utf-8')
    css = (ROOT / 'frontend/static/css/themes.css').read_text(encoding='utf-8')
    assert 'function _hbWeatherMood' in js
    assert 'function applyHummingbirdWeatherMood' in js
    assert 'loadWorldClockZones()' in js
    assert "document.body.dataset.hbWeather = spec.mood" in js
    assert '--hb-aura-a' in css and '--hb-aura-b' in css and '--hb-aura-c' in css
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
