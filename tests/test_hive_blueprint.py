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
    monkeypatch.setenv('SWARM_DB_PATH', str(tmp_path / 'swarm_memory.db'))
    import utils.db._connection as conn_mod
    conn_mod.DB_PATH = str(tmp_path / 'swarm_memory.db')
    import utils.db.trace_log as trace_log
    trace_log._SCHEMA_READY = False
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


def test_nodes_windows_runtime_uses_db_fallback(client, monkeypatch):
    monkeypatch.setenv('SWARM_PLATFORM', 'windows')
    payload = build_telemetry('node-win', 'windows')
    rv = client.post('/api/hive/telemetry', json=payload)
    assert rv.status_code == 200, rv.get_data(as_text=True)

    rv = client.get('/api/hive/nodes?expected=0')
    assert rv.status_code == 200
    j = rv.get_json()
    assert j['ok'] is True
    assert j['source'] == 'db-fallback-windows'
    assert [n['node_id'] for n in j['nodes']] == ['node-win']


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
    payload = build_telemetry(
        'potato-2', 'android',
        compute={'gpu_present': True},
        memory={'ram_total_mb': 6000, 'ram_free_mb': 1800},
        power={'battery_pct': 80},
        capabilities=['inference.cpu', 'inference.gpu', 'inference.tflite'],
    )
    client.post('/api/hive/telemetry', json=payload)

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tiny.gpu.benchmark',
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
    job = rv.get_json()['job']
    assert job['kind'] == 'tiny.gpu.benchmark'

    rv = client.post('/api/hive/jobs/report', json={
        'job_id': job['job_id'],
        'result': {'ok': True, 'runner': 'test-runner', 'gpu_probe': {'ok': True}},
    })
    assert rv.status_code == 200

    rv = client.get('/api/hive/jobs')
    assert rv.status_code == 200
    listed = rv.get_json()['jobs'][0]
    assert listed['payload']['packet'] == 'tiny'
    assert listed['result']['runner'] == 'test-runner'
    assert listed['result']['gpu_probe']['ok'] is True


def test_tiny_gpu_benchmark_full_loop_returns_capacity_proof(client):
    payload = build_telemetry(
        'potato-2', 'android',
        compute={'gpu_present': True},
        memory={'ram_total_mb': 6000, 'ram_free_mb': 1800},
        power={'battery_pct': 80},
        capabilities=['inference.cpu', 'inference.gpu', 'inference.tflite'],
    )
    client.post('/api/hive/telemetry', json=payload)

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tiny.gpu.benchmark',
        'payload': {
            'target_node': 'potato-2',
            'benchmark_sizes': [4, 16, 64, 128],
            'model_capsule': {
                'capsule_id': 'swarm-golden-linear-v1',
                'model': 'swarm-linear-4x4',
                'input': [0.18, 0.41, 0.73, 1.0],
                'weights': [
                    0.62, 0.10, 0.24, 0.02,
                    0.12, 0.58, 0.16, 0.04,
                    0.08, 0.18, 0.70, 0.02,
                    0.20, 0.14, 0.18, 0.48,
                ],
            },
        },
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200, rv.get_data(as_text=True)
    job_id = rv.get_json()['job_id']

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    job = rv.get_json()['job']
    assert job['job_id'] == job_id
    assert job['kind'] == 'tiny.gpu.benchmark'
    assert job['payload']['benchmark_sizes'] == [4, 16, 64, 128]
    assert job['payload']['model_capsule']['capsule_id'] == 'swarm-golden-linear-v1'

    gpu_probe = {
        'ok': True,
        'renderer': 'Mali-G68',
        'capacity_score': 100,
        'benchmark_ladder': [
            {'model_size': 4, 'ok': True, 'latency_ms': 5.6},
            {'model_size': 16, 'ok': True, 'latency_ms': 2.8},
            {'model_size': 64, 'ok': True, 'latency_ms': 3.0},
            {'model_size': 128, 'ok': True, 'latency_ms': 12.0},
        ],
        'tiny_model': {
            'model': 'tiny-gpu-linear-128x128',
            'model_size': 128,
            'latency_ms': 12.0,
            'delegate': 'gles-fragment-shader',
        },
        'model_capsule': {
            'ok': True,
            'capsule_id': 'swarm-golden-linear-v1',
            'model': 'swarm-linear-4x4',
            'delegate': 'gles-fragment-shader',
            'source': 'hive-payload',
            'output_rgba': [55, 73, 140, 151],
            'latency_ms': 1.2,
        },
    }
    rv = client.post('/api/hive/jobs/report', json={
        'job_id': job_id,
        'result': {'ok': True, 'runner': 'seven-app', 'gpu_probe': gpu_probe},
    })
    assert rv.status_code == 200
    assert rv.get_json()['ok'] is True

    rv = client.get('/api/hive/jobs?status=completed')
    assert rv.status_code == 200
    listed = rv.get_json()['jobs'][0]
    assert listed['job_id'] == job_id
    assert listed['payload']['target_node'] == 'potato-2'
    assert listed['result']['runner'] == 'seven-app'
    assert listed['result']['gpu_probe']['renderer'] == 'Mali-G68'
    assert listed['result']['gpu_probe']['capacity_score'] >= 80
    assert [
        row['model_size']
        for row in listed['result']['gpu_probe']['benchmark_ladder']
    ] == [4, 16, 64, 128]
    capsule = listed['result']['gpu_probe']['model_capsule']
    assert capsule['capsule_id'] == 'swarm-golden-linear-v1'
    assert capsule['source'] == 'hive-payload'
    assert capsule['output_rgba'] == [55, 73, 140, 151]


def test_gpu_routing_rejects_unhealthy_node(client):
    payload = build_telemetry(
        'potato-2', 'android',
        compute={'gpu_present': True},
        memory={'ram_total_mb': 6000, 'ram_free_mb': 1800},
        power={'battery_pct': 12},
        capabilities=['inference.cpu', 'inference.gpu', 'inference.tflite'],
    )
    client.post('/api/hive/telemetry', json=payload)

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tiny.gpu.benchmark',
        'payload': {'target_node': 'potato-2'},
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job'] is None


def test_gpu_routing_requires_capacity_before_inference(client):
    payload = build_telemetry(
        'potato-2', 'android',
        compute={'gpu_present': True},
        memory={'ram_total_mb': 6000, 'ram_free_mb': 1800},
        power={'battery_pct': 80},
        capabilities=['inference.cpu', 'inference.gpu', 'inference.tflite'],
    )
    client.post('/api/hive/telemetry', json=payload)

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tflite.inference',
        'payload': {'target_node': 'potato-2'},
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job'] is None


def test_tflite_gpu_packet_can_establish_capacity_then_inference_claims(client):
    payload = build_telemetry(
        'potato-2', 'android',
        compute={'gpu_present': True},
        memory={'ram_total_mb': 6000, 'ram_free_mb': 1800},
        power={'battery_pct': 80},
        capabilities=['inference.cpu', 'inference.gpu', 'inference.tflite'],
    )
    client.post('/api/hive/telemetry', json=payload)

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tflite.gpu',
        'payload': {'target_node': 'potato-2', 'benchmark_sizes': [4, 16, 64, 128]},
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200
    gpu_job_id = rv.get_json()['job_id']

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job']['job_id'] == gpu_job_id

    rv = client.post('/api/hive/jobs/report', json={
        'job_id': gpu_job_id,
        'result': {
            'ok': True,
            'runner': 'android-hive-apk',
            'gpu_probe': {'ok': True, 'capacity_score': 90},
        },
    })
    assert rv.status_code == 200

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tflite.inference',
        'payload': {'target_node': 'potato-2'},
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200
    infer_job_id = rv.get_json()['job_id']

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job']['job_id'] == infer_job_id


def test_stale_gpu_node_is_offline_and_cannot_claim(client):
    payload = build_telemetry(
        'potato-2', 'android',
        compute={'gpu_present': True},
        memory={'ram_total_mb': 6000, 'ram_free_mb': 1800},
        power={'battery_pct': 80},
        capabilities=['inference.cpu', 'inference.gpu', 'inference.tflite'],
        ts=1,
    )
    client.post('/api/hive/telemetry', json=payload)

    rv = client.get('/api/hive/nodes?expected=0')
    assert rv.status_code == 200
    node = rv.get_json()['nodes'][0]
    assert node['node_id'] == 'potato-2'
    assert node['offline'] is True

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tiny.gpu.benchmark',
        'payload': {'target_node': 'potato-2'},
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job'] is None


def test_hive_job_lifecycle_writes_studio_trace_events(client):
    payload = build_telemetry(
        'potato-2', 'android',
        compute={'gpu_present': True},
        memory={'ram_total_mb': 6000, 'ram_free_mb': 1800},
        power={'battery_pct': 80},
        capabilities=['inference.cpu', 'inference.gpu', 'inference.tflite'],
    )
    client.post('/api/hive/telemetry', json=payload)

    rv = client.post('/api/hive/jobs/submit', json={
        'kind': 'tiny.gpu.benchmark',
        'payload': {'target_node': 'potato-2'},
        'capability_req': 'inference.gpu',
    })
    assert rv.status_code == 200
    job_id = rv.get_json()['job_id']

    rv = client.post('/api/hive/jobs/next', json={
        'node_id': 'potato-2',
        'capabilities': ['inference.gpu', 'inference.tflite'],
    })
    assert rv.status_code == 200
    assert rv.get_json()['job']['job_id'] == job_id

    rv = client.post('/api/hive/jobs/report', json={
        'job_id': job_id,
        'result': {'ok': True, 'runner': 'seven-app'},
    })
    assert rv.status_code == 200
    assert rv.get_json()['ok'] is True

    from utils.db import trace_log
    events = trace_log.list_events(
        thread_id=job_id,
        change_id='P-HIVE-P2-GPU-LOOP',
    )
    stages = {e['payload'].get('stage') for e in events}
    assert {'submitted', 'claimed', 'completed'} <= stages
    assert {e['source'] for e in events} == {'hive'}
