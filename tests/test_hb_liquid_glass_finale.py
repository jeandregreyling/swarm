"""Tests for the Hummingbird Liquid-Glass Finale theme polish (living aurora, specular glass tiles, clocks, sundials, taskbar)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hummingbird_liquid_glass_finale_css_complete():
    css = (ROOT / 'frontend/static/css/themes.css').read_text(encoding='utf-8')
    for token in (
        '@keyframes hb-aurora-drift',
        'body.theme-hummingbird::before',
        'backdrop-filter: blur(24px) saturate(195%)',
        'body.theme-hummingbird .home-card',
        'body.theme-hummingbird .world-clock-item',
        'body.theme-hummingbird #sundial',
        'prefers-reduced-motion',
    ):
        assert token in css, f'Missing Liquid-Glass Finale token: {token}'
