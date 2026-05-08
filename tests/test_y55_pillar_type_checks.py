"""Y.55 — Type-check sweep for Y.40-pillar surfaces.

Continues the Y.50/Y.53/Y.54 hardening across the captured-pillar
blueprints (financial, trading, cybersecurity, business) and
media_curriculum. These all had the same `(body.get('x') or '').strip()`
crash-on-non-string bug. Cross-cutting fix; small surgical tests per
endpoint to lock the contract.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Real-DB-isolated client. The wishlist/captured-pillar blueprints
    use their own connect() helpers writing to swarm_memory.db; we
    override SWARM_DB so they hit the temp file instead."""
    db = str(tmp_path / 'y55.db')
    monkeypatch.setenv('SWARM_DB', db)
    monkeypatch.setenv('SWARM_DB_PATH', db)
    from frontend.terminal import create_app
    app = create_app()
    with app.test_client() as c:
        yield c


# ── financial_bp ──────────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('ticker', 99),
    ('asset_class', ['equity']),
    ('conviction', {'a': 1}),
    ('currency', 7),
    ('thesis', [1, 2]),
])
def test_financial_create_rejects_non_string(client, field, value):
    payload = {'ticker': 'AAPL', field: value}
    r = client.post('/api/financial/positions', json=payload)
    assert r.status_code == 400, r.get_data(as_text=True)


# ── trading_bp ────────────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('symbol', 99),
    ('side', ['buy']),
    ('strategy', {'k': 1}),
    ('notes', [1]),
])
def test_trading_create_rejects_non_string(client, field, value):
    payload = {'symbol': 'BTC', 'side': 'buy', field: value}
    r = client.post('/api/trading/signals', json=payload)
    assert r.status_code == 400


# ── cybersecurity_bp ──────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('summary', 99),
    ('severity', ['high']),
    ('source', {'k': 1}),
    ('detail', [1, 2]),
])
def test_cyber_create_rejects_non_string(client, field, value):
    payload = {'summary': 'breach detected', field: value}
    r = client.post('/api/cyber/events', json=payload)
    assert r.status_code == 400


# ── business_bp ───────────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('kind', 99),
    ('currency', ['USD']),
    ('counterparty', {'k': 1}),
    ('category', [1]),
    ('notes', {'a': 'b'}),
])
def test_business_create_rejects_non_string(client, field, value):
    payload = {'amount': 100.0, field: value}
    r = client.post('/api/business/entries', json=payload)
    assert r.status_code == 400


# ── media_curriculum ──────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('topic', 99),
    ('kind', ['music']),
    ('tool', {'k': 1}),
    ('notes', [1, 2]),
])
def test_media_curriculum_create_rejects_non_string(client, field, value):
    payload = {'topic': 'mixing', 'kind': 'music', 'tool': 'ableton',
               field: value}
    r = client.post('/api/kc/media/curriculum', json=payload)
    assert r.status_code == 400


@pytest.mark.parametrize('field,value', [
    ('asset_id', 99),
    ('project_id', ['p']),
    ('agent', {'a': 1}),
])
def test_media_curriculum_trace_rejects_non_string(client, field, value):
    payload = {'asset_id': 'A1', field: value}
    r = client.post('/api/kc/media/trace', json=payload)
    assert r.status_code == 400


# ── happy-path regression guards ─────────────────────────────────────

def test_financial_happy_path_still_works(client):
    r = client.post('/api/financial/positions', json={'ticker': 'AAPL'})
    assert r.status_code == 201


def test_trading_happy_path_still_works(client):
    r = client.post('/api/trading/signals', json={'symbol': 'BTC', 'side': 'buy'})
    assert r.status_code == 201


def test_cyber_happy_path_still_works(client):
    r = client.post('/api/cyber/events', json={'summary': 'fine'})
    assert r.status_code == 201


def test_business_happy_path_still_works(client):
    r = client.post('/api/business/entries', json={'amount': 1.0})
    assert r.status_code == 201


def test_media_curriculum_happy_path_still_works(client):
    r = client.post('/api/kc/media/curriculum',
                    json={'topic': 't', 'kind': 'music', 'tool': 'ableton'})
    assert r.status_code == 200
