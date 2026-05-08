"""Y.58e — sundial tooltip pointer-events.

Bug: user reported clicking Auto / Boost on the temp tooltip did nothing.

Root cause was upstream of the JS handlers we 'fixed' in Y.58d. The CSS rule
`.sundial-tooltip { pointer-events: none; }` made the tip and every button
inside it non-interactive — mouseenter, mouseleave and click events could
never fire. The buttons rendered but were literal pass-through ghosts.

This test locks the fix in place so a future cleanup pass can't quietly
re-introduce `pointer-events: none` and silently break Auto/Boost/Unload
again.
"""
from __future__ import annotations

from pathlib import Path

import re

CSS = Path('frontend/static/css/diamond.css').read_text(encoding='utf-8')


def _extract_block(name: str) -> str:
    m = re.search(r'\.' + re.escape(name) + r'\s*\{([^}]*)\}', CSS)
    assert m, f'expected to find .{name} block in diamond.css'
    return m.group(1)


def test_sundial_tooltip_is_interactive():
    block = _extract_block('sundial-tooltip')
    assert 'pointer-events: auto' in block, \
        '.sundial-tooltip must have pointer-events:auto so Auto/Boost/Unload buttons are clickable'
    assert 'pointer-events: none' not in block, \
        '.sundial-tooltip must NOT carry pointer-events:none — that made every button inert'


def test_attn_dot_keeps_pointer_events_none():
    """Regression guard: the attention-dot badge SHOULD keep pointer-events:none
    so it doesn't steal clicks from the tile underneath. Make sure we didn't
    accidentally flip the wrong rule."""
    block = _extract_block('attn-dot')
    assert 'pointer-events: none' in block, \
        '.attn-dot must keep pointer-events:none — only the tooltip needed flipping'
