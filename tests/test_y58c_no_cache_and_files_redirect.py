"""Y.58c — verify the HTML shell is no-cache and the Files openers redirect into KC.

The user kept seeing a stale tile layout after restart: the static cache-bust
versions had been bumped but the HTML page itself was a 200-and-cached. This
suite locks the no-cache header in place and confirms the spotlight + command
palette + standalone Files entry now route through the Knowledge Center
"files" tab so we don't quietly grow a ghost Files tile back into the UI.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope='module')
def client():
    from frontend.terminal import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_html_shell_is_no_cache(client):
    r = client.get('/ui')
    assert r.status_code == 200
    cc = (r.headers.get('Cache-Control') or '').lower()
    assert 'no-cache' in cc or 'no-store' in cc, f'expected no-cache HTML shell, got {cc!r}'


def test_command_palette_files_routes_to_knowledge():
    text = Path('frontend/static/js/core/init.js').read_text(encoding='utf-8')
    # Make sure the legacy direct-open call is gone and replaced by the KC tab.
    assert "'openWindow(\"files\", \"Files\", \"view-files\")'" not in text
    assert 'knowledgeSetTab("files")' in text


def test_spotlight_files_routes_to_knowledge():
    text = Path('frontend/static/js/views/spotlight.js').read_text(encoding='utf-8')
    assert "openWindow('files','Files','view-files')" not in text
    assert "knowledgeSetTab('files')" in text


def test_terminal_base_has_no_files_home_card():
    text = Path('frontend/templates/terminal_base.html').read_text(encoding='utf-8')
    # The Files home tile must not exist; only the hidden marker tiles for
    # the four pillars are allowed and they don't reference Files.
    assert 'data-win-id="files"' not in text


def test_sundial_layout_uses_150px():
    css = Path('frontend/static/css/diamond.css').read_text(encoding='utf-8')
    assert 'width: 150px' in css and 'height: 150px' in css, 'sundial wrap should be bumped to 150px'

    js = Path('frontend/static/js/views/diamond.js').read_text(encoding='utf-8')
    assert 'cx = 75, cy = 75, radius = 58' in js, 'sundial centre/radius must match the 150px wrap'
