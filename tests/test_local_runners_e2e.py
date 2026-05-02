"""End-to-end smokes for the local-runner endpoints.

MD-FEATURE-0037ADA58E14 — "add fuller end-to-end tests once real local
runners are attached." We don't require live ollama / lmstudio / picoclaw
processes here; the contract we test is that the Flask surface keeps a
predictable shape regardless of runner state, so live UAT can layer on top
of these without wondering whether the API itself shifted.
"""
from __future__ import annotations

import json
import pytest


@pytest.fixture(scope='module')
def client():
    from frontend.terminal import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()


def test_localai_status_shape(client):
    r = client.get('/api/localai/status')
    assert r.status_code == 200
    data = json.loads(r.get_data(as_text=True))
    assert data.get('ok') is True
    for runner in ('ollama', 'lmstudio', 'picoclaw'):
        assert runner in data
        assert 'running' in data[runner]
        assert isinstance(data[runner]['running'], bool)


def test_localai_available_models_shape(client):
    r = client.get('/api/localai/available-models')
    assert r.status_code == 200
    data = json.loads(r.get_data(as_text=True))
    # Endpoint must always return a JSON object (ok flag may be true even
    # when no runners are reachable — registered list still works).
    assert isinstance(data, dict)


def test_localai_ollama_chat_rejects_empty(client):
    r = client.post('/api/localai/ollama/chat', json={})
    # Either 400 (empty prompt) or 200 with ok:false. Either way it must
    # not 500 / crash on missing fields.
    assert r.status_code in (200, 400)


def test_localai_lmstudio_chat_rejects_empty(client):
    r = client.post('/api/localai/lmstudio/chat', json={})
    assert r.status_code in (200, 400)


def test_kc_media_curriculum_round_trip(client):
    """KC media curriculum endpoint round-trip — ties learning context to
    the local runners that produce media (covered by Y.36)."""
    r = client.post('/api/kc/media/curriculum',
                    json={'topic': 'e2e-test-genre', 'kind': 'genre',
                          'tool': 'e2e-test-tool', 'notes': 'smoke'})
    assert r.status_code == 200
    data = json.loads(r.get_data(as_text=True))
    assert data.get('ok') is True
    rl = client.get('/api/kc/media/curriculum?kind=genre')
    assert rl.status_code == 200
    listing = json.loads(rl.get_data(as_text=True))
    topics = {it['topic'] for it in listing.get('items', [])}
    assert 'e2e-test-genre' in topics


def test_kc_media_trace_round_trip(client):
    rt = client.post('/api/kc/media/trace',
                     json={'asset_id': 'e2e-asset-001',
                           'topics': ['lo-fi'], 'tools': ['e2e-test-tool'],
                           'agent': 'mistral'})
    assert rt.status_code == 200
    data = json.loads(rt.get_data(as_text=True))
    assert data.get('ok') is True and data.get('trace_id', '').startswith('TRACE-')
    rl = client.get('/api/kc/media/trace?asset_id=e2e-asset-001')
    listing = json.loads(rl.get_data(as_text=True))
    assert any(it['asset_id'] == 'e2e-asset-001' for it in listing.get('items', []))


def test_hive_resolve_invalid_inputs(client):
    """STEP-KC-TOPICS-HIVE-NAVIGATION-20260430 covered by Y.34."""
    assert client.get('/api/hive/resolve?kind=robot&id=1').status_code == 400
    assert client.get('/api/hive/resolve?kind=topic&id=abc').status_code == 400
    assert client.get('/api/hive/resolve?kind=topic&id=999999').status_code == 404
