"""Tests for frontend.blueprints.hive HTTP surface — Y.59."""
from __future__ import annotations

import os

import pytest

from core.hive import build_telemetry
from core.hive.registry import HiveRegistry


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate DB + token store from production data.
    monkeypatch.setenv('SWARM_HIVE_DB', str(tmp_path / 'hive.db'))
    monkeypatch.setenv('SWARM_HIVE_TOKENS', str(tmp_path / 'tokens.jsonl'))
    # Reset registry singleton so the env-var takes effect.
    import core.hive.registry as reg_mod
    reg_mod.reset_singleton()

    from flask import Flask
    from frontend.blueprints.hive import hive_bp
    app = Flask(__name__)
    app.register_blueprint(hive_bp)
    app.testing = True
    return app.test_client()


def test_local_endpoint(client):
    rv = client.get('/api/hive/local')
    assert rv.status_code == 200
    j = rv.get_json()
    assert j['ok']
    assert j['telemetry']['contract'] == 'node.resource/v0'


def test_telemetry_post_and_list(client):
    payload = build_telemetry('node-test', 'linux',
                              compute={'cpu_peak_temp_c': 60})
    rv = client.post('/api/hive/telemetry', json=payload)
    assert rv.status_code == 200, rv.get_data(as_text=True)
    rv = client.get('/api/hive/nodes')
    j = rv.get_json()
    assert j['ok']
    assert any(n['node_id'] == 'node-test' for n in j['nodes'])


def test_telemetry_post_rejects_invalid(client):
    rv = client.post('/api/hive/telemetry', json={'not': 'valid'})
    assert rv.status_code in (400, 422)


def test_telemetry_post_rejects_non_json(client):
    rv = client.post('/api/hive/telemetry', data='nope',
                     content_type='text/plain')
    assert rv.status_code == 400


def test_get_node_404(client):
    rv = client.get('/api/hive/node/nonsuch')
    assert rv.status_code == 404


def test_policy_via_kwargs(client):
    payload = build_telemetry('n1', 'linux')
    client.post('/api/hive/telemetry', json=payload)
    rv = client.post('/api/hive/policy', json={
        'node_id': 'n1', 'fan_mode': 'boost', 'boost_exit_temp_c': 80,
    })
    assert rv.status_code == 200, rv.get_data(as_text=True)


def test_policy_unknown_node_404(client):
    rv = client.post('/api/hive/policy', json={
        'node_id': 'ghost', 'fan_mode': 'boost',
    })
    assert rv.status_code == 404


def test_enrol_returns_token(client):
    rv = client.post('/api/hive/enrol', json={
        'node_id': 'n2', 'label': 'tester', 'platform': 'linux',
    })
    assert rv.status_code == 200
    j = rv.get_json()
    assert j['ok']
    assert isinstance(j['token'], str) and len(j['token']) > 20


def test_delete_unknown(client):
    rv = client.delete('/api/hive/node/nope')
    assert rv.status_code == 404


def test_delete_existing(client):
    payload = build_telemetry('togo', 'linux')
    client.post('/api/hive/telemetry', json=payload)
    rv = client.delete('/api/hive/node/togo')
    assert rv.status_code == 200
    rv2 = client.get('/api/hive/node/togo')
    assert rv2.status_code == 404


def test_submit_job_can_target_node(client):
    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tflite.inference',
        'payload': {'target_node': 'potato-2', 'packet': 'tiny'},
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200, rv.get_data(as_text=True)
    j = rv.get_json()
    assert j['ok']
    assert j['node_id'] == 'potato-2'

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-1',
        'capabilities': ['inference.gpu'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job'] is None

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job']['kind'] == 'tflite.inference'
