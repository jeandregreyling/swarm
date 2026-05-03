"""Y.58d — sundial tooltip stay-alive + ray-edge cleanup.

User report: hovering Temp shows the boost popup, but moving the cursor toward
Auto / Boost makes the tooltip vanish before the click registers, and the rays
look 'funky' because they pass straight through the centre disc and through
the dot.

These tests lock in the source-level fix:

- `_hideSundialTip` must track a timer id and `clearTimeout` it when the tip
  is re-entered, otherwise the fixed delay always wins the race.
- The tip must overlap the node (no dead-zone gap), so a slow cursor doesn't
  fall off the edge of either element while travelling between them.
- Rays must start at the centre-disc edge and stop at the dot edge, not run
  through both.

Source-level checks are the convention in this repo because we have no
jsdom; tests/test_taskbar_launcher_coverage.py and tests/test_v7c_r2_home_header.py
follow the same pattern.
"""
from __future__ import annotations

from pathlib import Path

import pytest

DIAM = Path('frontend/static/js/views/diamond.js').read_text(encoding='utf-8')


def test_hide_timer_is_tracked_and_cancellable():
    """The fixed-delay setTimeout was the bug. Now the timer id must be stored
    on the tip and clearable from mouseenter."""
    assert 'tip._hideTimer' in DIAM, '_hideSundialTip must store the timer id on the tip'
    # mouseenter should clear it.
    assert "clearTimeout(tip._hideTimer)" in DIAM, 'mouseenter must clearTimeout(tip._hideTimer)'
    # The fixed setTimeout pattern from before must be gone.
    assert 'setTimeout(() => { if (!tip._hover) tip.style.display' not in DIAM, \
        'old fixed-delay tooltip hide pattern still present'


def test_tooltip_overlaps_node_no_dead_zone():
    """Tip must overlap the node by ~4px so the cursor never crosses an empty
    pixel column on its way to the Auto / Boost buttons."""
    assert 'rect.top - tipH + 4' in DIAM, \
        'tooltip top should overlap node by ~4px (no -8 gap)'
    assert 'rect.top - tipH - 8' not in DIAM, \
        'old 8px tooltip gap must be removed'


def test_rays_use_inner_outer_endpoints():
    """Rays must stop at the centre-disc edge / dot edge, not run through both."""
    assert 'RAY_INNER' in DIAM and 'RAY_OUTER' in DIAM, \
        'sundial rays must use trimmed inner/outer endpoints'
    # The naive 'from centre to node' line must be gone.
    assert "line.setAttribute('x1', cx);  line.setAttribute('y1', cy)" not in DIAM, \
        'old ray endpoint (cx,cy) -> (nx,ny) still present; rays still pass through centre disc'


def test_hide_grace_increased():
    """The hide grace should be at least 250ms so a slow cursor wins."""
    import re
    matches = re.findall(r'_hideTimer\s*=\s*setTimeout\(\s*\(\)\s*=>\s*\{[^}]*\},\s*(\d+)\)', DIAM)
    assert matches, 'expected _hideTimer setTimeout entries'
    for ms in matches:
        assert int(ms) >= 120, f'hide grace too tight: {ms}ms'
    # At least one >= 300ms (the main hide path).
    assert any(int(ms) >= 300 for ms in matches), \
        f'main _hideSundialTip grace should be >=300ms, got {matches}'


def test_fan_boost_buttons_present_on_temp():
    """Regression: Y.58 fan-boost buttons must still be rendered for the temp metric."""
    assert "metric.key === 'temp'" in DIAM
    assert 'stip-fan-btn' in DIAM
    assert "data-mode=\"boost\"" in DIAM and "data-mode=\"auto\"" in DIAM
    assert "/api/fan/mode" in DIAM
