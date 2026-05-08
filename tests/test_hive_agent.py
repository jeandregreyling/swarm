"""Tests for ops/hive_agent.py — portable Hive node agent."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
AGENT_PATH = REPO / 'ops' / 'hive_agent.py'


@pytest.fixture(scope='session')
def hive_agent():
    spec = importlib.util.spec_from_file_location('hive_agent', AGENT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv('SWARM_HIVE_AGENT_DIR', str(tmp_path / 'cfg'))
    monkeypatch.delenv('SWARM_HIVE_LEADER', raising=False)
    monkeypatch.delenv('SWARM_HIVE_TOKEN', raising=False)
    monkeypatch.delenv('SWARM_NODE_ID', raising=False)
    return tmp_path / 'cfg'


def test_load_config_missing_returns_empty(hive_agent, isolated_config):
    assert hive_agent.load_config() == {}


def test_save_then_load_roundtrip(hive_agent, isolated_config):
    hive_agent.save_config({'leader': 'http://x', 'token': 'abc'})
    cfg = hive_agent.load_config()
    assert cfg['leader'] == 'http://x'
    assert cfg['token'] == 'abc'
    # File must be 0o600 on POSIX
    if os.name == 'posix':
        mode = (isolated_config / 'agent.json').stat().st_mode & 0o777
        assert mode == 0o600


def test_save_corrupt_json_recovers(hive_agent, isolated_config):
    isolated_config.mkdir(parents=True, exist_ok=True)
    (isolated_config / 'agent.json').write_text('{not json')
    assert hive_agent.load_config() == {}


def test_agent_post_once_uses_token(hive_agent, isolated_config):
    captured = {}

    def fake_transport(method, url, *, payload=None, token=None, timeout=10.0):
        captured['method'] = method
        captured['url'] = url
        captured['payload'] = payload
        captured['token'] = token
        return {'ok': True, 'ts': 12345}

    agent = hive_agent.HiveAgent(
        leader='http://example/',
        token='secrettok',
        node_id='test-node',
        interval=10,
        transport=fake_transport,
    )
    reply = agent.post_once()
    assert reply == {'ok': True, 'ts': 12345}
    assert captured['method'] == 'POST'
    assert captured['url'] == 'http://example/api/hive/telemetry'
    assert captured['token'] == 'secrettok'
    assert captured['payload']['contract'] == 'node.resource/v0'
    assert captured['payload']['node_id'] == 'test-node'


def test_agent_falls_back_to_config(hive_agent, isolated_config):
    hive_agent.save_config({
        'leader': 'http://from-config:9000',
        'token': 'cfg-token',
        'node_id': 'cfg-node',
    })
    agent = hive_agent.HiveAgent()
    assert agent.leader == 'http://from-config:9000'
    assert agent.token == 'cfg-token'
    assert agent.node_id == 'cfg-node'


def test_agent_env_overrides_config(hive_agent, isolated_config, monkeypatch):
    hive_agent.save_config({'leader': 'http://cfg:1', 'token': 'cfg'})
    monkeypatch.setenv('SWARM_HIVE_LEADER', 'http://env:2')
    monkeypatch.setenv('SWARM_HIVE_TOKEN', 'envtok')
    agent = hive_agent.HiveAgent()
    assert agent.leader == 'http://env:2'
    assert agent.token == 'envtok'


def test_enrol_persists_token(hive_agent, isolated_config, monkeypatch):
    monkeypatch.setattr(hive_agent, '_http',
                        lambda *a, **kw: {'ok': True, 'token': 'minted-tok'})
    out = hive_agent.enrol('http://leader:5050/', node_id='n-1')
    assert out['token'] == 'minted-tok'
    assert out['node_id'] == 'n-1'
    cfg = hive_agent.load_config()
    assert cfg['token'] == 'minted-tok'
    assert cfg['leader'] == 'http://leader:5050'
    assert cfg['node_id'] == 'n-1'


def test_enrol_rejects_response_without_token(hive_agent, isolated_config, monkeypatch):
    monkeypatch.setattr(hive_agent, '_http',
                        lambda *a, **kw: {'ok': True})
    with pytest.raises(hive_agent.AgentError):
        hive_agent.enrol('http://leader:5050')


def test_main_show_emits_valid_envelope(hive_agent, isolated_config, capsys):
    rc = hive_agent.main(['--show', '--node-id', 'show-node'])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data['node_id'] == 'show-node'
    assert data['contract'] == 'node.resource/v0'
    assert 'compute' in data and 'thermal' in data


def test_agent_post_once_via_main(hive_agent, isolated_config, monkeypatch, capsys):
    monkeypatch.setenv('SWARM_HIVE_LEADER', 'http://leader:5050')

    def fake_http(method, url, *, payload=None, token=None, timeout=10.0):
        return {'ok': True, 'ts': 42}

    monkeypatch.setattr(hive_agent, '_http', fake_http)
    rc = hive_agent.main(['--once', '--interval', '10'])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {'ok': True, 'ts': 42}
