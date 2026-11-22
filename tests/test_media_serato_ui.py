"""Tests for Phase 1C Serato-Inspired Dual-Deck Waveform & YouTube Studio UI."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_serato_js_syntax_and_endpoints():
    js_path = ROOT / 'frontend/static/js/views/media-serato-decks.js'
    src = js_path.read_text(encoding='utf-8')
    assert '/api/media-center/library' in src
    assert '/api/media-center/decks/mix' in src
    assert '/render-video' in src
    assert '/dsp' in src
    node = shutil.which('node')
    if node:
        res = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_serato_css_balanced_and_template_wired():
    css = (ROOT / 'frontend/static/css/views/media-serato.css').read_text(encoding='utf-8')
    assert css.count('{') == css.count('}')
    assert '.serato-studio-shell' in css
    assert '.serato-wave-canvas' in css
    tpl = (ROOT / 'frontend/templates/terminal_base.html').read_text(encoding='utf-8')
    assert 'media-serato.css' in tpl
    assert 'media-serato-decks.js' in tpl
    assert 'id="media-serato-studio"' in tpl
