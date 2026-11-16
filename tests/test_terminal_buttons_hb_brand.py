"""Acceptance test for the terminal buttons step (owner 16 Nov 2026): "let apex make the allow button a bit more on brand for HB".
APEX copies this file to tests/test_terminal_buttons_hb_brand.py in its change.

Main chat's terminal buttons ("Allow and run" = .hc-terminal-allow, "Stop" = .hc-terminal-stop, core/hb_chat_terminal.py) follow the HB
brand pack (core/capability_packs/hb.brand.v1.json): theme colours only (var(--accent) and the theme variables, no hard-coded colours),
an HB line icon drawn with currentColor (a small flower on Allow), a gentle hover, and no motion for people who prefer reduced motion."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / 'frontend' / 'static' / 'css' / 'home-chat.css').read_text()


def _rules(name):
    return [body for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', CSS) if name in selector]


def test_both_buttons_are_styled_with_theme_colours_only():
    for name in ('.hc-terminal-allow', '.hc-terminal-stop'):
        rules = _rules(name)
        assert rules, f'{name} has no style'
        text = ' '.join(rules)
        assert 'var(--accent)' in text or name == '.hc-terminal-stop'
        assert not re.search(r'#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(', text), f'{name} hard-codes a colour'
    assert any(':hover' in sel for sel, _ in re.findall(r'([^{}]+)\{([^{}]*)\}', CSS) if '.hc-terminal-allow' in sel)


def test_allow_carries_an_hb_line_icon_in_the_theme_colour():
    icon = ' '.join(body for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', CSS) if '.hc-terminal-allow' in sel and '::before' in sel)
    assert 'currentColor' in icon and 'mask' in icon and 'svg' in icon


def test_motion_respects_reduced_motion():
    moving = any(re.search(r'\b(animation|transition)\s*:', body) for body in _rules('.hc-terminal-'))
    if moving:
        blocks = re.findall(r'@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\}\s*\}', CSS, re.S)
        assert any('hc-terminal' in b for b in blocks), 'buttons move, but not switched off for reduced motion'
