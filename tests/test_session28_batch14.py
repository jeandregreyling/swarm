"""Session 28 batch 14 — wishlist pillars promoted from capture-only to active v0.

Tests cover all four pillar blueprints (cyber, financial, trading, business),
the aggregated /api/wishlist/summary endpoint, Seven's _load_pillars_context
+ fast-path, and the front-end live-panel wiring.

Pillars are intentionally additive: a pristine DB without any pillar tables
should still answer summary calls (they create the table on first touch),
and a corrupt DB should degrade rather than 500.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
PILLAR_LIVE_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'pillar_live.js'

# Ensure the repo root, then `frontend`, are importable. Order matters: the
# repo root must come FIRST so that `agents` resolves to the namespace
# package, not to frontend/blueprints/agents.py which would shadow it.
for sub in ('', 'frontend'):
    p = str(ROOT / sub) if sub else str(ROOT)
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the pillar store at a throw-away DB and reset import cache."""
    db = tmp_path / 'pillars.db'
    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))
    # Pillar modules cache nothing at import-time, but make sure any prior
    # test's connection pool is gone.
    for mod in list(sys.modules):
        if mod.startswith('blueprints.') and mod.endswith('_bp'):
            sys.modules.pop(mod, None)
        if mod == 'blueprints._pillar_store':
            sys.modules.pop(mod, None)
    yield db


def _flask_app(blueprint_module: str, blueprint_attr: str):
    from flask import Flask
    app = Flask(__name__)
    bp = getattr(importlib.import_module(blueprint_module), blueprint_attr)
    app.register_blueprint(bp)
    return app.test_client()


# ──────────────────────────────────────────────────────────────────────
# Cyber Security pillar
# ──────────────────────────────────────────────────────────────────────

def test_cyber_create_list_summary(isolated_db):
    client = _flask_app('blueprints.cybersecurity_bp', 'cybersecurity_bp')
    r = client.post('/api/cyber/events', json={'summary': 'test', 'severity': 'high'})
    assert r.status_code == 201
    event_id = r.get_json()['event_id']
    assert event_id.startswith('CYB-')
    r = client.get('/api/cyber/events')
    body = r.get_json()
    assert body['ok'] and body['count'] == 1 and body['events'][0]['event_id'] == event_id
    r = client.get('/api/cyber/summary')
    s = r.get_json()
    assert s['pillar'] == 'cyber-security' and s['ok'] and s['open'] == 1
    assert s['by_severity']['high'] == 1


def test_cyber_validates_severity(isolated_db):
    client = _flask_app('blueprints.cybersecurity_bp', 'cybersecurity_bp')
    r = client.post('/api/cyber/events', json={'summary': 'x', 'severity': 'BANANAS'})
    assert r.status_code == 400 and r.get_json()['ok'] is False


def test_cyber_requires_summary(isolated_db):
    client = _flask_app('blueprints.cybersecurity_bp', 'cybersecurity_bp')
    r = client.post('/api/cyber/events', json={})
    assert r.status_code == 400


def test_cyber_patch_and_delete(isolated_db):
    client = _flask_app('blueprints.cybersecurity_bp', 'cybersecurity_bp')
    eid = client.post('/api/cyber/events', json={'summary': 'x'}).get_json()['event_id']
    r = client.patch(f'/api/cyber/events/{eid}', json={'status': 'resolved'})
    assert r.status_code == 200 and 'status' in r.get_json()['updated']
    r = client.delete(f'/api/cyber/events/{eid}')
    assert r.status_code == 200
    r = client.delete(f'/api/cyber/events/{eid}')
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# Financial pillar
# ──────────────────────────────────────────────────────────────────────

def test_financial_create_high_conviction_surfaces(isolated_db):
    client = _flask_app('blueprints.financial_bp', 'financial_bp')
    r = client.post('/api/financial/positions', json={
        'ticker': 'AAPL', 'asset_class': 'equity', 'conviction': 'high',
        'notional': 1000000, 'currency': 'USD', 'thesis': 'AI capex'
    })
    assert r.status_code == 201
    s = client.get('/api/financial/summary').get_json()
    assert s['ok'] and s['open'] == 1 and len(s['high_conviction']) == 1
    assert s['high_conviction'][0]['ticker'] == 'AAPL'


def test_financial_rejects_bad_asset_class(isolated_db):
    client = _flask_app('blueprints.financial_bp', 'financial_bp')
    r = client.post('/api/financial/positions',
                    json={'ticker': 'X', 'asset_class': 'cattle-futures'})
    assert r.status_code == 400


def test_financial_rejects_non_numeric_notional(isolated_db):
    client = _flask_app('blueprints.financial_bp', 'financial_bp')
    r = client.post('/api/financial/positions', json={'ticker': 'X', 'notional': 'big'})
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Trading pillar
# ──────────────────────────────────────────────────────────────────────

def test_trading_signal_lifecycle(isolated_db):
    client = _flask_app('blueprints.trading_bp', 'trading_bp')
    sid = client.post('/api/trading/signals', json={
        'symbol': 'BTC-USD', 'side': 'buy', 'confidence': 0.75
    }).get_json()['signal_id']
    assert sid.startswith('TRD-')
    r = client.patch(f'/api/trading/signals/{sid}', json={'status': 'closed', 'pnl': 250.5})
    assert r.status_code == 200
    s = client.get('/api/trading/summary').get_json()
    assert s['ok'] and s['realised_pnl'] == 250.5
    assert s['open'] == 0  # closed pulled it out of open


def test_trading_confidence_bounded(isolated_db):
    client = _flask_app('blueprints.trading_bp', 'trading_bp')
    r = client.post('/api/trading/signals',
                    json={'symbol': 'X', 'side': 'buy', 'confidence': 1.5})
    assert r.status_code == 400


def test_trading_rejects_bad_side(isolated_db):
    client = _flask_app('blueprints.trading_bp', 'trading_bp')
    r = client.post('/api/trading/signals', json={'symbol': 'X', 'side': 'levitate'})
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Business pillar
# ──────────────────────────────────────────────────────────────────────

def test_business_ledger_summary(isolated_db):
    client = _flask_app('blueprints.business_bp', 'business_bp')
    eid = client.post('/api/business/entries', json={
        'kind': 'expense', 'amount': -49.99, 'currency': 'USD',
        'counterparty': 'anthropic', 'category': 'cloud'
    }).get_json()['entry_id']
    client.patch(f'/api/business/entries/{eid}', json={'status': 'posted'})
    s = client.get('/api/business/summary').get_json()
    assert s['ok'] and s['net_by_currency']['USD'] == -49.99
    assert s['by_kind']['expense'] == 1


def test_business_rejects_bad_kind(isolated_db):
    client = _flask_app('blueprints.business_bp', 'business_bp')
    r = client.post('/api/business/entries', json={'kind': 'tribute'})
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Aggregated wishlist summary
# ──────────────────────────────────────────────────────────────────────

def test_wishlist_summary_aggregates_four_pillars(isolated_db):
    from flask import Flask
    from blueprints.wishlist_bp import wishlist_bp
    app = Flask(__name__)
    app.register_blueprint(wishlist_bp)
    client = app.test_client()
    body = client.get('/api/wishlist/summary').get_json()
    assert body['ok'] is True
    assert body['status'] == 'active-v0'
    assert set(body['pillars'].keys()) == {'cyber-security', 'financial', 'trading', 'business'}
    # All four should report ok=True against a fresh DB (they create their tables).
    for slug, snap in body['pillars'].items():
        assert snap['ok'] is True, f'{slug} failed: {snap}'


def test_wishlist_pillars_listing_status_active(isolated_db):
    from flask import Flask
    from blueprints.wishlist_bp import wishlist_bp
    app = Flask(__name__)
    app.register_blueprint(wishlist_bp)
    client = app.test_client()
    body = client.get('/api/wishlist/pillars').get_json()
    assert body['ok'] and body['status'] == 'active-v0' and body['count'] == 4


# ──────────────────────────────────────────────────────────────────────
# Seven integration
# ──────────────────────────────────────────────────────────────────────

def test_seven_loads_pillars_context(isolated_db, monkeypatch):
    # Reload seven_agent so our env-var-isolated DB applies.
    sys.modules.pop('agents.seven.seven_agent', None)
    seven = importlib.import_module('agents.seven.seven_agent')
    pillars = seven._load_pillars_context()
    assert set(pillars.keys()) == {'cyber-security', 'financial', 'trading', 'business'}
    block = seven._format_pillars_block(pillars)
    assert 'Cyber Security' in block
    assert 'Trading' in block


def test_seven_pillars_slash_command(isolated_db):
    sys.modules.pop('agents.seven.seven_agent', None)
    seven = importlib.import_module('agents.seven.seven_agent')
    out = seven._slash_command('/pillars')
    assert out is not None
    assert 'Wishlist pillars' in out
    assert '/api/wishlist/summary' in out


# ──────────────────────────────────────────────────────────────────────
# Front-end wiring
# ──────────────────────────────────────────────────────────────────────

def test_pillar_live_js_exists_and_handles_four_slugs():
    text = PILLAR_LIVE_JS.read_text()
    for slug in ('cyber-security', 'financial', 'trading', 'business'):
        assert f"'{slug}'" in text


def test_template_has_live_panels_and_loader():
    text = TEMPLATE.read_text()
    for slug in ('cyber-security', 'financial', 'trading', 'business'):
        assert f'data-live-slug="{slug}"' in text
    assert 'pillar_live.js' in text
    # tiles flipped from capture-only to active-v0
    # Updated count: money-hub is a 5th home-card-wishlist active-v0 tile
    # added after this test was written (audit P-308466EE76 / Area 1 fix — 2026-05-10)
    assert text.count('data-wishlist-status="active-v0"') == 5
    assert 'data-wishlist-status="capture-only"' not in text


def test_blueprint_registry_includes_four_pillars():
    text = (ROOT / 'frontend' / 'terminal.py').read_text()
    for needle in ('cybersecurity_bp', 'financial_bp', 'trading_bp', 'business_bp'):
        assert re.search(rf"\(['\"]blueprints\.{needle}['\"]\s*,\s*['\"]?{needle}['\"]?\)", text), needle


# ──────────────────────────────────────────────────────────────────────
# Continuous improvement doc
# ──────────────────────────────────────────────────────────────────────

def test_continuous_improvement_doc_exists():
    doc = ROOT / 'docs' / 'continuous-improvement.md'
    assert doc.exists()
    text = doc.read_text()
    assert 'pillar' in text.lower()
    assert 'ensure_columns' in text  # references the schema-forward pattern
