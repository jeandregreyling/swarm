"""Y.49 — Orientation tile + manual orientation entry tests.

STEP-DOCS-UX-BC3D33C260 — User said the Help tile is hard to find on first
launch and the search bar was confusing. The fix is:

1. A new `orientation` entry in the single-source manual that explains:
   where Help (`?`) lives, what the Spotlight search bar does, and where the
   taskbar is.
2. A small first-run flag (`/api/orientation/*`) so the home tile can show a
   dismissable orientation card that points at those things, then stay hidden
   once dismissed (with a version bump escape hatch for future changes).

These tests lock the API + manual contract.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    monkeypatch.chdir(ROOT)
    import sys as _sys
    from frontend.terminal import create_app
    app = create_app()
    # Patch services.get_connection — orientation uses it; also patch the
    # local binding inside the loaded `blueprints.orientation` module (which
    # imported `get_connection` by name at module load time).
    import services as _svc
    factory = lambda: sqlite3.connect(tmp.name)  # noqa: E731
    monkeypatch.setattr(_svc, 'get_connection', factory)
    for mod_name in ('blueprints.orientation', 'frontend.blueprints.orientation'):
        if mod_name in _sys.modules:
            monkeypatch.setattr(
                _sys.modules[mod_name], 'get_connection', factory, raising=False,
            )
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_orientation_manual_entry_present(client):
    """The single-source manual must serve the orientation entry — this is
    what the '?' help button + Manual tile both consume."""
    r = client.get('/api/manual/orientation')
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['ok']
    assert body['key'] == 'orientation'
    assert body['title']
    # Must reference the three things the user was confused about
    text = (body['title'] + ' ' + body['body']).lower()
    assert 'help' in text or '?' in body['body']
    assert 'spotlight' in text or 'search' in text
    assert 'taskbar' in text or 'tile' in text


def test_orientation_listed_in_manual_keys(client):
    """The manual key list must include 'orientation' so contextual help and
    docs viewers can render it."""
    r = client.get('/api/manual')
    assert r.status_code == 200
    keys = r.get_json()['keys']
    assert 'orientation' in keys


def test_orientation_seen_is_false_initially(client):
    r = client.get('/api/orientation/seen').get_json()
    assert r['ok']
    assert r['seen'] is False
    assert r['version']


def test_orientation_dismiss_then_seen(client):
    d = client.post('/api/orientation/dismiss').get_json()
    assert d['ok'] and d['seen'] is True
    assert d['seen_at'] > 0
    s = client.get('/api/orientation/seen').get_json()
    assert s['seen'] is True
    assert s['version'] == d['version']


def test_orientation_reset_makes_unseen_again(client):
    client.post('/api/orientation/dismiss')
    r = client.post('/api/orientation/reset').get_json()
    assert r['ok'] and r['reset'] is True
    s = client.get('/api/orientation/seen').get_json()
    assert s['seen'] is False


def test_orientation_per_user(client):
    """Per-user state: dismissing for one user must NOT mark another as seen."""
    client.post('/api/orientation/dismiss?user=alice')
    sa = client.get('/api/orientation/seen?user=alice').get_json()
    sb = client.get('/api/orientation/seen?user=bob').get_json()
    assert sa['seen'] is True
    assert sb['seen'] is False


def test_orientation_version_bump_invalidates(client, monkeypatch):
    """If the active orientation version moves ahead of what the user
    previously dismissed, treat as not-seen so the new card shows again."""
    client.post('/api/orientation/dismiss')
    import sys as _sys
    mod = _sys.modules.get('blueprints.orientation') or \
          _sys.modules.get('frontend.blueprints.orientation')
    monkeypatch.setattr(mod, '_VERSION', 'v2')
    s = client.get('/api/orientation/seen').get_json()
    assert s['seen'] is False
    assert s['version'] == 'v2'
    assert s.get('previous_version') == 'v1'


def test_orientation_card_rendered_in_template():
    """The home template must include the orientation card markup AND load
    its JS controller so the contract from the API actually drives UI."""
    template = os.path.join(ROOT, 'frontend', 'templates', 'terminal_base.html')
    with open(template, encoding='utf-8') as f:
        html = f.read()
    assert 'id="orientation-card"' in html
    assert 'id="orientation-card-dismiss"' in html
    assert 'id="orientation-card-open-manual"' in html
    assert 'orientation_card.js' in html


def test_orientation_card_js_exists_and_calls_endpoints():
    """The JS controller must hit the three endpoints we ship."""
    js = os.path.join(ROOT, 'frontend', 'static', 'js', 'views', 'orientation_card.js')
    assert os.path.exists(js)
    with open(js, encoding='utf-8') as f:
        body = f.read()
    assert '/api/orientation/seen' in body
    assert '/api/orientation/dismiss' in body
