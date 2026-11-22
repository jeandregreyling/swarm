"""Tests for Defect 5: World Clocks instant weather on city change (Manila), uniform alignment, and modern Hummingbird Help."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_world_clocks_refresh_weather_and_align_uniformly():
    js_path = ROOT / 'frontend/static/js/core/theme.js'
    js = js_path.read_text(encoding='utf-8')
    assert "if (typeof _fetchClockWeather === 'function') _fetchClockWeather();" in js
    assert 'class="clock-weather-row"' in js and 'min-height:14px' in js
    assert 'weather.temperature ?? weather.temp' in js
    assert 'weather.weathercode ?? weather.code' in js
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
    wp = (ROOT / 'frontend/blueprints/weather_bp.py').read_text(encoding='utf-8')
    assert "'manila':" in wp


def test_help_modal_uses_modern_hummingbird_copy_not_legacy_fridays():
    studio_path = ROOT / 'frontend/static/js/views/studio.js'
    src = studio_path.read_text(encoding='utf-8')
    assert "title: 'Hummingbird (HB) Home'" in src
    assert "title: 'Fridays Home'" not in src
    assert 'Write @gemma' not in src
    chk = subprocess.run(['node', '--check', str(studio_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
