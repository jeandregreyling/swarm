"""Y.46 — Wishlist registry consistency lock.

The wishlist registry endpoint (Y.40) claims certain blueprints + routes
exist in the running app. If a future rename or extraction breaks the
mapping, the audit closeout for the 9 captured pillars becomes a lie.

This test loads the registry response and asserts every claimed
blueprint is registered and every claimed route is mounted.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope='module')
def app_state():
    from frontend.terminal import create_app
    app = create_app()
    return app


def test_wishlist_registry_endpoint_returns_pillars(app_state):
    with app_state.test_client() as c:
        r = c.get('/api/wishlist/registry')
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True
    assert body['count'] >= 9
    assert 'S-45064ED6C5' in body['kept_open']


def test_wishlist_registry_blueprints_are_registered(app_state):
    with app_state.test_client() as c:
        body = c.get('/api/wishlist/registry').get_json()
    have = set(app_state.blueprints.keys())
    for pillar in body['pillars']:
        bp = pillar['blueprint']
        assert bp in have, f"{pillar['pillar']} claims blueprint {bp!r} but it is not registered"


def test_wishlist_registry_routes_are_mounted(app_state):
    """Every advertised route must resolve to a registered URL rule.

    Routes can include query strings (e.g. ?kind=accounting) which we
    strip before matching, since flask's url_map keys on path only.
    """
    with app_state.test_client() as c:
        body = c.get('/api/wishlist/registry').get_json()
    rules = {r.rule for r in app_state.url_map.iter_rules()}
    missing = []
    for pillar in body['pillars']:
        for route in pillar.get('routes', []):
            path = route.split('?', 1)[0]
            if path not in rules:
                missing.append((pillar['pillar'], route))
    assert not missing, f'Wishlist registry references unmounted routes: {missing}'
