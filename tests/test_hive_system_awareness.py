"""Tests for HB system awareness, potato-node enrollment, APEX/FRED/HB role models, and peer sharing."""
from __future__ import annotations

import sqlite3
from unittest import mock

import pytest
from flask import Flask

from core import hb_roles
from core.hive.contract import ContractError, build_telemetry, validate_telemetry
from core.hive.node_enrollment import (
    discover_peer_capabilities,
    enroll_local_node,
    enrolled_node_id,
    enrolled_role_models,
    find_peer_for_model,
    load_enrollment,
)
from core.hive.system_profile import (
    _classify_gpu,
    _classify_tier,
    build_shareable_manifest,
    recommend_role_models,
)


def _dell_hw():
    return {
        'hostname': 'dell-7090',
        'os': 'windows',
        'manufacturer': 'Dell Inc.',
        'model': 'OptiPlex 7090',
        'cpu_model': 'Intel Core i5-10500',
        'cpu_cores': 6,
        'cpu_threads': 12,
        'ram_total_mb': 32504,
        'ram_free_mb': 16000,
        'gpus': [_classify_gpu('Intel(R) UHD Graphics 630', 1024)],
        'has_discrete_gpu': False,
        'primary_backend': 'cpu',
        'tier': 'cpu-workstation',
    }


def _dell_runtimes():
    return {
        'ollama': {'online': True, 'url': 'http://127.0.0.1:11434', 'loaded': []},
        'llama_servers': [],
        'models': [
            {'name': 'Llama3.2:latest', 'provider': 'ollama', 'size_gb': 1.88, 'fit': 'fast', 'embed': False, 'loaded': False},
            {'name': 'qwen:latest', 'provider': 'ollama', 'size_gb': 2.17, 'fit': 'fast', 'embed': False, 'loaded': False},
            {'name': 'gemma3:latest', 'provider': 'ollama', 'size_gb': 3.11, 'fit': 'fast', 'embed': False, 'loaded': False},
            {'name': 'Qwen2.5:latest', 'provider': 'ollama', 'size_gb': 4.36, 'fit': 'fast', 'embed': False, 'loaded': False},
            {'name': 'gemma4:26b', 'provider': 'ollama', 'size_gb': 16.75, 'fit': 'tight', 'embed': False, 'loaded': False},
            {'name': 'Qwen3.6:latest', 'provider': 'ollama', 'size_gb': 22.29, 'fit': 'too-large', 'embed': False, 'loaded': False},
            {'name': 'nomic-embed-text:latest', 'provider': 'ollama', 'size_gb': 0.26, 'fit': 'fast', 'embed': True, 'loaded': False},
        ],
    }


def test_gpu_and_tier_classification():
    igpu = _classify_gpu('Intel(R) UHD Graphics 630', 1024)
    assert igpu['discrete'] is False
    assert igpu['backend'] == 'igpu'
    assert _classify_tier(32504, [igpu]) == 'cpu-workstation'
    assert _classify_tier(16384, [igpu]) == 'potato-node'

    amd_gpu = _classify_gpu('AMD Radeon RX 7900 XTX', 24576)
    assert amd_gpu['discrete'] is True
    assert _classify_tier(65536, [amd_gpu]) == 'gpu-workstation'


def test_recommend_role_models_on_dell_potato():
    rec = recommend_role_models(_dell_hw(), _dell_runtimes())
    # APEX should pick fast-fit Qwen2.5, not 22 GB Qwen3.6 or embedding model
    assert rec['apex']['model'] == 'Qwen2.5:latest'
    assert rec['apex']['fit'] == 'fast'
    # FRED should pick strongest model that fits in 32 GB RAM (gemma4:26b, not 22.29 GB too-large)
    assert rec['fred']['model'] == 'gemma4:26b'
    # HB should pick fastest lightweight model (Llama3.2) and never nomic-embed
    assert rec['hb']['model'] == 'Llama3.2:latest'


def test_recommend_role_models_prefers_llama8080_on_gpu_rig():
    gpu = _classify_gpu('AMD Radeon RX 7900 XTX', 24576)
    hw = {**_dell_hw(), 'gpus': [gpu], 'has_discrete_gpu': True, 'primary_backend': 'rocm', 'tier': 'gpu-workstation', 'ram_total_mb': 65536}
    rt = {
        'ollama': {'online': False, 'url': 'http://127.0.0.1:11434', 'loaded': []},
        'llama_servers': [{'endpoint': 'http://127.0.0.1:8080', 'online': True, 'models': ['gpt-oss:20b']}],
        'models': [
            {'name': 'gpt-oss:20b', 'provider': 'llamacpp', 'endpoint': 'http://127.0.0.1:8080', 'size_gb': 13.0, 'fit': 'fast', 'embed': False, 'loaded': True},
            {'name': 'fred-cpu:24b', 'provider': 'llamacpp', 'endpoint': '', 'size_gb': 15.0, 'fit': 'tight', 'embed': False, 'loaded': False},
            {'name': 'homework-cpu:7b', 'provider': 'llamacpp', 'endpoint': '', 'size_gb': 4.5, 'fit': 'fast', 'embed': False, 'loaded': False},
        ],
    }
    rec = recommend_role_models(hw, rt)
    assert rec['apex']['model'] == 'gpt-oss:20b'
    assert rec['fred']['model'] == 'fred-cpu:24b'
    assert rec['hb']['model'] == 'homework-cpu:7b'


def test_contract_optional_system_profile_and_shareable():
    base = build_telemetry('potato-4', 'windows')
    assert 'system_profile' not in base
    assert 'shareable' not in base

    enriched = build_telemetry(
        'potato-4', 'windows',
        system_profile={'hardware': _dell_hw()},
        shareable={'accept_remote_jobs': True, 'shared_models': []},
    )
    validate_telemetry(enriched)
    assert enriched['system_profile']['hardware']['model'] == 'OptiPlex 7090'
    assert enriched['shareable']['accept_remote_jobs'] is True

    bad = dict(enriched, shareable='not-a-dict')
    with pytest.raises(ContractError):
        validate_telemetry(bad)


def test_enroll_local_node_and_hb_roles_integration(tmp_path, monkeypatch):
    enr_file = tmp_path / 'node_enrollment.json'
    monkeypatch.setenv('SWARM_NODE_ENROLLMENT', str(enr_file))

    fake_profile = {
        'ts': 1700000000,
        'hardware': _dell_hw(),
        'runtimes': _dell_runtimes(),
        'recommended_models': recommend_role_models(_dell_hw(), _dell_runtimes()),
    }
    with mock.patch('core.hive.node_enrollment.collect_system_profile', return_value=fake_profile):
        res = enroll_local_node(
            node_id='potato-4',
            label='potato-4 Dell OptiPlex 7090',
            role='worker',
            leader_url='http://192.168.1.10:5050',
            endpoint_url='http://192.168.1.44:5050',
            path=enr_file,
            sync_db=False,
            record_registry=False,
        )

    assert enrolled_node_id(enr_file) == 'potato-4'
    loaded = load_enrollment(enr_file)
    assert loaded['label'] == 'potato-4 Dell OptiPlex 7090'
    assert loaded['models'] == {'apex': 'Qwen2.5:latest', 'fred': 'gemma4:26b', 'hb': 'Llama3.2:latest'}
    assert res['enrollment']['shareable']['endpoint_url'] == 'http://192.168.1.44:5050'

    role_map = enrolled_role_models(enr_file)
    assert role_map['apex'] == 'Qwen2.5:latest'
    assert role_map['deep'] == 'gemma4:26b'
    assert role_map['homework'] == 'Llama3.2:latest'
    assert role_map['hb'] == 'Llama3.2:latest'

    # hb_roles.resolve uses enrolled models when hb_roles DB table has no explicit row
    conn = sqlite3.connect(':memory:')
    model, why = hb_roles.resolve('apex', conn=conn, known=lambda m: m == 'Qwen2.5:latest')
    assert model == 'Qwen2.5:latest'
    assert 'enrollment' in why

    f_model, _ = hb_roles.resolve('deep', conn=conn, known=lambda m: m == 'gemma4:26b')
    assert f_model == 'gemma4:26b'

    hb_model, _ = hb_roles.resolve('hb', conn=conn, known=lambda m: m == 'Llama3.2:latest')
    assert hb_model == 'Llama3.2:latest'


def test_peer_capability_discovery_and_model_matching():
    amd_share = {
        'endpoint_url': 'http://192.168.1.10:5050',
        'tier': 'gpu-workstation',
        'primary_backend': 'rocm',
        'accept_remote_jobs': True,
        'role_models': {'apex': 'gpt-oss:20b', 'fred': 'fred-cpu:24b', 'hb': 'homework-cpu:7b'},
        'shared_models': [
            {'name': 'gpt-oss:20b', 'provider': 'llamacpp', 'size_gb': 13.0, 'fit': 'fast', 'loaded': True},
            {'name': 'Qwen3.6:latest', 'provider': 'ollama', 'size_gb': 22.29, 'fit': 'fast', 'loaded': False},
        ],
    }
    dell_share = build_shareable_manifest(_dell_hw(), _dell_runtimes(), {
        'endpoint_url': 'http://192.168.1.44:5050',
        'models': {'apex': 'Qwen2.5:latest', 'fred': 'gemma4:26b', 'hb': 'Llama3.2:latest'},
    })
    nodes = [
        {
            'node_id': 'potato-1', 'label': 'AMD Leader', 'platform': 'linux', 'offline': False,
            'telemetry': {'memory': {'ram_total_mb': 65536, 'ram_free_mb': 42000}, 'capabilities': ['inference.gpu'], 'shareable': amd_share},
        },
        {
            'node_id': 'potato-4', 'label': 'Dell OptiPlex 7090', 'platform': 'windows', 'offline': False,
            'telemetry': {'memory': {'ram_total_mb': 32504, 'ram_free_mb': 16000}, 'capabilities': ['inference.cpu', 'inference.ollama'], 'shareable': dell_share},
        },
    ]

    peers = discover_peer_capabilities(nodes)
    assert len(peers) == 2
    match_big = find_peer_for_model('Qwen3.6:latest', nodes, exclude_node_id='potato-4')
    assert match_big is not None
    assert match_big['node_id'] == 'potato-1'
    assert match_big['primary_backend'] == 'rocm'

    match_small = find_peer_for_model('Llama3.2:latest', nodes, exclude_node_id='potato-1')
    assert match_small is not None
    assert match_small['node_id'] == 'potato-4'


def test_hive_blueprint_enrollment_and_peer_routes(tmp_path, monkeypatch):
    from frontend.blueprints.hive import hive_bp

    enr_file = tmp_path / 'node_enrollment.json'
    monkeypatch.setenv('SWARM_NODE_ENROLLMENT', str(enr_file))
    monkeypatch.setenv('SWARM_HIVE_DB', str(tmp_path / 'hive.db'))

    app = Flask(__name__)
    app.register_blueprint(hive_bp)
    client = app.test_client()

    fake_profile = {
        'ts': 1700000000,
        'hardware': _dell_hw(),
        'runtimes': _dell_runtimes(),
        'recommended_models': recommend_role_models(_dell_hw(), _dell_runtimes()),
    }
    with mock.patch('core.hive.system_profile.collect_system_profile', return_value=fake_profile), \
         mock.patch('core.hive.node_enrollment.collect_system_profile', return_value=fake_profile):
        r1 = client.get('/api/hive/system-profile')
        assert r1.status_code == 200
        assert r1.get_json()['hardware']['model'] == 'OptiPlex 7090'

        r2 = client.post('/api/hive/enrollment', json={
            'node_id': 'potato-4',
            'label': 'potato-4 Dell',
            'role': 'worker',
            'models': {'apex': 'Qwen2.5:latest', 'fred': 'gemma4:26b', 'hb': 'Llama3.2:latest'},
        })
        assert r2.status_code == 200
        body = r2.get_json()
        assert body['ok'] is True
        assert body['enrollment']['node_id'] == 'potato-4'
        assert body['enrollment']['models']['apex'] == 'Qwen2.5:latest'

        r3 = client.get('/api/hive/enrollment')
        assert r3.status_code == 200
        assert r3.get_json()['enrolled'] is True

        r4 = client.get('/api/hive/peers/capabilities?model=Qwen2.5:latest')
        assert r4.status_code == 200
        assert r4.get_json()['ok'] is True


def test_self_sampler_tick_pushes_to_leader_for_worker(tmp_path, monkeypatch):
    from core.hive import self_sampler
    from core.hive.node_enrollment import save_enrollment
    from core.hive.local_node import reset_local_node

    enr_file = tmp_path / 'node_enrollment.json'
    monkeypatch.setenv('SWARM_NODE_ENROLLMENT', str(enr_file))
    monkeypatch.setenv('SWARM_HIVE_DB', str(tmp_path / 'hive.db'))
    monkeypatch.delenv('SWARM_NODE_ID', raising=False)
    save_enrollment({
        'enrolled': True,
        'node_id': 'potato-4',
        'label': 'potato-4 Dell',
        'role': 'worker',
        'leader_url': 'http://10.0.0.8:5050',
        'models': {'apex': 'Qwen2.5:latest', 'fred': 'gemma4:26b', 'hb': 'Llama3.2:latest'},
    }, path=enr_file)
    reset_local_node()

    pushed = {}

    def _fake_push(**kwargs):
        pushed.update(kwargs)
        return {'ok': True, 'status': 200, 'leader_url': kwargs.get('leader_url')}

    with mock.patch('core.hive.node_enrollment.push_telemetry_to_leader', side_effect=_fake_push):
        res = self_sampler._tick()
        assert res['node_id'] == 'potato-4'
        assert res['leader_push']['ok'] is True
        assert pushed['leader_url'] == 'http://10.0.0.8:5050'
        assert pushed['node_id'] == 'potato-4'
    reset_local_node()


def test_onboarding_welcome_aboard_packager_routes(tmp_path, monkeypatch):
    from frontend.blueprints.onboarding import onboarding_bp
    from core.hive.local_node import reset_local_node

    enr_file = tmp_path / 'node_enrollment.json'
    monkeypatch.setenv('SWARM_NODE_ENROLLMENT', str(enr_file))
    monkeypatch.setenv('SWARM_HIVE_DB', str(tmp_path / 'hive.db'))
    monkeypatch.setenv('SWARM_HIVE_DISABLE_SELF_SAMPLER', '1')
    reset_local_node()

    app = Flask(__name__)
    app.register_blueprint(onboarding_bp)
    client = app.test_client()

    fake_profile = {
        'ts': 1700000000,
        'hardware': _dell_hw(),
        'runtimes': _dell_runtimes(),
        'recommended_models': recommend_role_models(_dell_hw(), _dell_runtimes()),
    }
    with mock.patch('core.hive.system_profile.collect_system_profile', return_value=fake_profile), \
         mock.patch('core.hive.node_enrollment.collect_system_profile', return_value=fake_profile), \
         mock.patch('core.hive.node_enrollment.push_telemetry_to_leader', return_value={'ok': True, 'status': 200, 'leader_url': 'http://10.0.0.8:5050'}):
        r_pkg = client.get('/api/onboarding/packager')
        assert r_pkg.status_code == 200
        pkg = r_pkg.get_json()
        assert pkg['ok'] is True
        assert pkg['enrolled'] is False
        ollama_check = next(c for c in pkg['preflight'] if c['id'] == 'ollama')
        assert ollama_check['status'] == 'ok'
        assert pkg['recommended_models']['apex']['model'] == 'Qwen2.5:latest'

        r_conn = client.post('/api/onboarding/packager/connect', json={
            'node_id': 'potato-4',
            'label': 'potato-4 Dell OptiPlex 7090',
            'role': 'worker',
            'leader_url': 'http://10.0.0.8:5050',
            'endpoint_url': 'http://10.0.0.9:5050',
            'models': {'apex': 'Qwen2.5:latest', 'fred': 'gemma4:26b', 'hb': 'Llama3.2:latest'},
        })
        assert r_conn.status_code == 200
        conn_body = r_conn.get_json()
        assert conn_body['ok'] is True
        assert conn_body['enrollment']['node_id'] == 'potato-4'
        assert conn_body['leader_push']['ok'] is True

        r_after = client.get('/api/onboarding/packager')
        assert r_after.get_json()['enrolled'] is True
    reset_local_node()
