"""Session 28 batch 13 — wishlist tiles + pillar API.

Covers:
- /api/wishlist/pillars               returns 4 pillars with the right slugs
- /api/wishlist/pillars/<slug>        returns single pillar
- /api/wishlist/pillars/<bad>         returns 404
- Pillars hydrate description + step records when DB rows exist
- Pillars degrade gracefully when DB rows are missing (placeholder stub)
- The 4 home tiles + 4 view templates exist in terminal_base.html
- The wishlist.js loader is referenced exactly once

These are placeholder-only tiles — the tests assert the placeholder
contract, not feature behaviour.
"""
from __future__ import annotations

import importlib
import os
import re
import sqlite3
from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
JS_LOADER = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'wishlist.js'

EXPECTED_SLUGS = {'cyber-security', 'financial', 'trading', 'business'}


# ── Helpers ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def wishlist_app(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT,
            description TEXT,
            status TEXT,
            owner TEXT,
            order_idx INTEGER,
            created_at REAL,
            updated_at REAL
        )"""
    )
    conn.executemany(
        "INSERT INTO project_steps(step_id, project_id, title, description, status, owner, order_idx, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [
            ('S-4697ECA1EC', 'P-X', 'Cyber Security as Diamond Layer', 'threat model + IDS', 'todo', 'seven', 0, 0),
            ('S-98CF85A8C4', 'P-X', 'Financial Analytics IB',          'M&A pipeline view',  'todo', 'seven', 1, 0),
            ('S-03A241D177', 'P-X', 'Online Trading',                  'order routing',      'todo', 'seven', 2, 0),
            ('S-D618CF4B7A', 'P-X', 'Business Operational Centre',     'we-can-do-anything', 'todo', 'seven', 3, 0),
            ('S-25AFB74A4D', 'P-X', 'Accounting + Payroll',            'double-entry ledger','todo', 'seven', 4, 0),
            ('S-642D6439DE', 'P-X', 'Manage People',                   'employee files',     'todo', 'seven', 5, 0),
            ('S-B6D5701E4F', 'P-X', 'Policies + Legal',                'sign-offs',          'todo', 'seven', 6, 0),
            ('S-5393AEF947', 'P-X', 'Stock + Vendors',                 'POs',                'todo', 'seven', 7, 0),
            ('S-2B6BC7A021', 'P-X', 'Products + Sales',                'catalogue',          'todo', 'seven', 8, 0),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from frontend.blueprints import wishlist_bp as wl_mod
    importlib.reload(wl_mod)
    app = Flask(__name__)
    app.register_blueprint(wl_mod.wishlist_bp)
    return app.test_client()


# ── API contract ────────────────────────────────────────────────────────────

def test_pillars_endpoint_returns_four_slugs(wishlist_app):
    r = wishlist_app.get('/api/wishlist/pillars')
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True
    assert body['count'] == 4
    slugs = {p['slug'] for p in body['pillars']}
    assert slugs == EXPECTED_SLUGS
    assert body['epic_step_id'] == 'S-45064ED6C5'


def test_pillar_endpoint_returns_steps_in_declared_order(wishlist_app):
    r = wishlist_app.get('/api/wishlist/pillars/business')
    body = r.get_json()
    assert body['ok'] is True
    ids = [s['step_id'] for s in body['steps']]
    # Declared in the blueprint: parent first, then accounting, people,
    # policies, stock, products.
    assert ids == [
        'S-D618CF4B7A',
        'S-25AFB74A4D',
        'S-642D6439DE',
        'S-B6D5701E4F',
        'S-5393AEF947',
        'S-2B6BC7A021',
    ]
    # Single-step pillars must still resolve.
    r = wishlist_app.get('/api/wishlist/pillars/cyber-security')
    body = r.get_json()
    assert [s['step_id'] for s in body['steps']] == ['S-4697ECA1EC']


def test_pillar_endpoint_includes_metadata(wishlist_app):
    r = wishlist_app.get('/api/wishlist/pillars/financial')
    body = r.get_json()
    assert body['tile_title'] == 'Financial Analytics'
    assert 'investment' in body['tile_subtitle'].lower() or 'Investment' in body['tile_subtitle']
    assert 'IB' in body['description'] or 'investment' in body['description'].lower()


def test_unknown_pillar_returns_404(wishlist_app):
    r = wishlist_app.get('/api/wishlist/pillars/does-not-exist')
    assert r.status_code == 404
    body = r.get_json()
    assert body['ok'] is False


def test_pillar_endpoint_handles_missing_db_rows(tmp_path, monkeypatch):
    """If project_steps doesn't have the expected step_ids, the API must
    still return the pillar with stub entries instead of crashing."""
    db = tmp_path / 'empty.db'
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE project_steps (step_id TEXT PRIMARY KEY, project_id TEXT,"
        " title TEXT, description TEXT, status TEXT, owner TEXT, order_idx INTEGER,"
        " created_at REAL, updated_at REAL)"
    )
    conn.commit(); conn.close()

    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from frontend.blueprints import wishlist_bp as wl_mod
    importlib.reload(wl_mod)
    app = Flask(__name__)
    app.register_blueprint(wl_mod.wishlist_bp)
    client = app.test_client()

    r = client.get('/api/wishlist/pillars/cyber-security')
    body = r.get_json()
    assert body['ok'] is True
    assert len(body['steps']) == 1
    assert body['steps'][0]['step_id'] == 'S-4697ECA1EC'
    assert body['steps'][0]['title'] == '(not yet captured)'


def test_pillar_endpoint_survives_missing_table(tmp_path, monkeypatch):
    """Fresh repo with no project_steps table: API must not 500."""
    db = tmp_path / 'bare.db'
    sqlite3.connect(db).close()
    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from frontend.blueprints import wishlist_bp as wl_mod
    importlib.reload(wl_mod)
    app = Flask(__name__)
    app.register_blueprint(wl_mod.wishlist_bp)
    client = app.test_client()

    r = client.get('/api/wishlist/pillars')
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True
    assert body['count'] == 4


# ── Template wiring ─────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def template_html() -> str:
    return TEMPLATE.read_text(encoding='utf-8')


@pytest.mark.parametrize('win_id,template_id', [
    ('wishlist-cyber',     'view-wishlist-cyber'),
    ('wishlist-financial', 'view-wishlist-financial'),
    ('wishlist-trading',   'view-wishlist-trading'),
    ('wishlist-business',  'view-wishlist-business'),
])
def test_wishlist_tile_present(template_html, win_id, template_id):
    assert ('data-win-id="' + win_id + '"') in template_html
    assert ('data-win-template="' + template_id + '"') in template_html
    assert ('<template id="' + template_id + '">') in template_html


def test_all_wishlist_tiles_marked_active_v0(template_html):
    """Tiles were promoted from capture-only to active-v0 in batch 14."""
    matches = re.findall(r'home-card home-card-wishlist[^>]*data-wishlist-status="active-v0"', template_html)
    assert len(matches) == 4, f"expected 4 active-v0 tiles, found {len(matches)}"
    assert 'data-wishlist-status="capture-only"' not in template_html


def test_wishlist_tiles_use_wishlist_badge(template_html):
    # Each pillar tile body should carry a Wishlist badge so users can't
    # confuse them with shipped surfaces.
    for slug_marker in ('wishlist-cyber', 'wishlist-financial', 'wishlist-trading', 'wishlist-business'):
        idx = template_html.find('data-win-id="' + slug_marker + '"')
        assert idx > -1
        block = template_html[idx:idx + 1200]
        assert 'wishlist-badge' in block, f"tile {slug_marker} missing Wishlist badge"


def test_wishlist_js_loader_referenced_once(template_html):
    refs = re.findall(r'/static/js/views/wishlist\.js', template_html)
    assert len(refs) == 1, f"expected exactly one wishlist.js reference, got {len(refs)}"


def test_wishlist_js_loader_exists():
    assert JS_LOADER.exists()
    body = JS_LOADER.read_text(encoding='utf-8')
    assert 'wishlistPopulateAll' in body
    assert '/api/wishlist/pillars/' in body
