"""Y.57 — agents.py POST type-check sweep (Y.50 cont.).

Five more agents.py admin/data endpoints had the Y.50-class
AttributeError-on-non-string crash. Same hardening template applied.
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
    db = str(tmp_path / 'y57.db')
    monkeypatch.setenv('SWARM_DB', db)
    monkeypatch.setenv('SWARM_DB_PATH', db)
    from frontend.terminal import create_app
    app = create_app()
    with app.test_client() as c:
        yield c


# ── /api/agents/config POST ───────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('name', 99),
    ('label', ['x']),
    ('model', {'k': 1}),
    ('role', [1]),
    ('system_prompt', 7),
    ('api_key_var', {'a': 1}),
    ('tier', [1]),
])
def test_agents_config_post_rejects_non_string(client, field, value):
    payload = {'name': 'fooagent', 'model': 'gpt-4', field: value}
    r = client.post('/api/agents/config', json=payload)
    assert r.status_code == 400, r.get_data(as_text=True)


# ── /api/agents/key/<name> PUT ────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('key_var', 99),
    ('value', ['x']),
])
def test_agents_key_put_rejects_non_string(client, field, value):
    payload = {'key_var': 'FOO_KEY', 'value': 'sk-xxx', field: value}
    r = client.put('/api/agents/key/qwen', json=payload)
    assert r.status_code == 400


# ── /api/agents/<agent>/memory/write POST ─────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('content', 99),
    ('tags', ['a']),
    ('type', {'k': 1}),
    ('subject', [1]),
])
def test_agents_memory_write_rejects_non_string(client, field, value):
    payload = {'content': 'note', field: value}
    r = client.post('/api/agents/qwen/memory/write', json=payload)
    assert r.status_code == 400


# ── /api/agents/bootstrap POST ────────────────────────────────────────

@pytest.mark.parametrize('value', [99, ['x'], {'a': 1}])
def test_agents_bootstrap_rejects_non_string_name(client, value):
    r = client.post('/api/agents/bootstrap', json={'name': value})
    assert r.status_code == 400


# ── /api/agents/hot-swap POST ─────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('from_agent', 99),
    ('to_agent', ['x']),
])
def test_agents_hot_swap_rejects_non_string(client, field, value):
    payload = {'from_agent': 'gemma', 'to_agent': 'qwen', field: value}
    r = client.post('/api/agents/hot-swap', json=payload)
    assert r.status_code == 400
