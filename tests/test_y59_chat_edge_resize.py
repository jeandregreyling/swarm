"""Y.59 chat-edge resize smoke tests — markup + CSS + JS contracts."""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_template_has_top_and_bottom_edges():
    html = (ROOT / 'frontend/templates/terminal_base.html').read_text()
    assert 'home-chat-edge home-chat-edge-top' in html
    assert 'home-chat-edge home-chat-edge-bottom' in html
    assert 'data-edge="top"' in html
    assert 'data-edge="bottom"' in html


def test_legacy_resizer_hidden():
    html = (ROOT / 'frontend/templates/terminal_base.html').read_text()
    assert 'home-chat-resizer-legacy' in html
    # display:none keeps the legacy id available without showing it.
    assert 'display:none' in html or 'display: none' in html


def test_css_has_edge_rules():
    css = (ROOT / 'frontend/static/css/home-chat.css').read_text()
    assert '.home-chat-edge' in css
    assert '.home-chat-edge-top' in css
    assert '.home-chat-edge-bottom' in css
    assert 'cursor:ns-resize' in css or 'cursor: ns-resize' in css


def test_js_binds_both_edges():
    js = (ROOT / 'frontend/static/js/views/diamond.js').read_text()
    assert 'home-chat-edge-top' in js
    assert 'home-chat-edge-bottom' in js
    assert 'fridays-home-chat-height' in js
    # bindHandle helper used for both edges:
    assert 'bindHandle' in js
