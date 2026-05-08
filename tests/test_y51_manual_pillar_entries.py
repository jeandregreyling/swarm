"""Y.51 — Manual entries for new pillars.

Y.47 added App Center, Y.43 added Synth Board + Video Editor, but the
single-source manual (`manual_content.MANUAL`) had no entries for them.
The orientation card (Y.49) tells users "the ? icon on every tile opens the
manual" — so missing entries break that promise. This batch adds them and
locks the contract with tests.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest


@pytest.fixture
def client():
    from frontend.terminal import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize('key,must_contain', [
    ('app-center',   ['mobile', 'framework', 'build']),
    ('synth-board',  ['oscillator', 'revision']),
    ('video-editor', ['timeline', 'render']),
])
def test_manual_serves_new_pillar_entry(client, key, must_contain):
    r = client.get(f'/api/manual/{key}')
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['ok']
    assert body['title']
    text = (body['title'] + ' ' + body['body']).lower()
    for needle in must_contain:
        assert needle in text, f"manual[{key}] missing keyword {needle!r}"


def test_manual_keys_includes_all_new_pillars(client):
    keys = client.get('/api/manual').get_json()['keys']
    for k in ('app-center', 'synth-board', 'video-editor', 'orientation'):
        assert k in keys


def test_manual_404s_for_unknown_keys(client):
    """Regression: unknown keys must still 404 cleanly, not 500."""
    r = client.get('/api/manual/this-tile-does-not-exist')
    assert r.status_code == 404
    body = r.get_json()
    assert body['ok'] is False


def test_manual_app_center_describes_archive_block(client):
    """Y.50 fix: archived projects don't accept builds. Manual mentions it."""
    body = client.get('/api/manual/app-center').get_json()['body'].lower()
    assert 'archive' in body
