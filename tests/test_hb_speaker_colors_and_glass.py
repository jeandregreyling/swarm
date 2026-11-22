"""Tests for speaker colour-coding, Hummingbird Liquid-Glass depth, and Clipboard S-xxxx codes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_speaker_colors_and_clipboard_step_codes_in_hb_live_js():
    js = (ROOT / 'frontend/static/js/hb-live.js').read_text(encoding='utf-8')
    assert 'b.dataset.hbSpeaker = speakerKey(b)' in js
    assert 'class="hbl-step-code"' in js
    assert 'raw === \'apex\'' in js
    assert 'raw === \'hummingbird\'' in js


def test_speaker_tints_and_liquid_glass_aurora_in_themes_css():
    css = (ROOT / 'frontend/static/css/themes.css').read_text(encoding='utf-8')
    for speaker in ('apex', 'hummingbird', 'copilot', 'user'):
        assert f'[data-hb-speaker="{speaker}"]' in css
    assert 'radial-gradient(circle at 14% 18%, rgba(16, 232, 164, 0.16)' in css
    assert 'backdrop-filter: blur(22px) saturate(185%)' in css
