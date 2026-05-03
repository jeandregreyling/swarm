"""Install-route tests for frontend.blueprints.hive — Y.59 visibility phase."""
from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('SWARM_HIVE_DB', str(tmp_path / 'hive.db'))
    monkeypatch.setenv('SWARM_HIVE_TOKENS', str(tmp_path / 'tokens.jsonl'))
    import core.hive.registry as reg_mod
    reg_mod.reset_singleton()
    from flask import Flask
    from frontend.blueprints.hive import hive_bp
    app = Flask(__name__)
    app.register_blueprint(hive_bp)
    app.testing = True
    return app.test_client()


def test_install_manifest_has_required_keys(client):
    rv = client.get('/api/hive/install/')
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['ok'] is True
    assert 'leader' in body
    assert 'one_liners' in body
    assert 'linux_macos' in body['one_liners']
    assert 'windows' in body['one_liners']
    names = {f['name'] for f in body['files']}
    for required in (
        'agent.py', 'install_linux.sh', 'install_macos.sh',
        'install_windows.ps1', 'bootstrap.sh', 'bootstrap.ps1',
    ):
        assert required in names, f'missing {required}'
    # Every advertised file must actually exist on the leader.
    for entry in body['files']:
        assert entry['available'] is True, f"{entry['name']} not available"
        assert entry['size'] and entry['size'] > 0


def test_install_manifest_no_trailing_slash_works(client):
    # Both /install and /install/ should resolve.
    rv = client.get('/api/hive/install')
    assert rv.status_code == 200


def test_install_serves_agent_py(client):
    rv = client.get('/api/hive/install/agent.py')
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert 'class HiveAgent' in body
    assert rv.mimetype.startswith('text/')


def test_install_serves_linux_installer(client):
    rv = client.get('/api/hive/install/install_linux.sh')
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert body.startswith('#!/usr/bin/env bash') or body.startswith('#!/bin/bash')


def test_install_serves_macos_installer(client):
    rv = client.get('/api/hive/install/install_macos.sh')
    assert rv.status_code == 200
    assert rv.get_data(as_text=True).startswith('#!')


def test_install_serves_windows_installer(client):
    rv = client.get('/api/hive/install/install_windows.ps1')
    assert rv.status_code == 200
    # PowerShell file — just confirm it's non-empty text.
    assert len(rv.get_data(as_text=True)) > 50


def test_install_bootstrap_sh_contents(client):
    rv = client.get('/api/hive/install/bootstrap.sh')
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert body.startswith('#!')
    assert 'SWARM_HIVE_LEADER' in body
    assert 'install_linux.sh' in body or 'install_${PLATFORM}.sh' in body


def test_install_bootstrap_ps1_contents(client):
    rv = client.get('/api/hive/install/bootstrap.ps1')
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert 'SWARM_HIVE_LEADER' in body
    assert 'install_windows.ps1' in body


def test_install_unknown_asset_404(client):
    rv = client.get('/api/hive/install/totally_made_up.py')
    assert rv.status_code == 404


def test_install_path_traversal_rejected(client):
    # A traversal attempt must not escape the allowlist.
    rv = client.get('/api/hive/install/..%2F..%2Fetc%2Fpasswd')
    assert rv.status_code == 404
    rv = client.get('/api/hive/install/../../etc/passwd')
    # Flask normalises the URL; whichever way it resolves, we must not
    # leak filesystem content. Anything except 404/308 is suspect.
    assert rv.status_code in (301, 308, 404)
    if rv.status_code in (301, 308):
        # If it redirects, follow once and confirm the target is also safe.
        rv2 = client.get(rv.headers['Location'])
        assert rv2.status_code == 404


def test_install_one_liner_uses_request_host(client):
    rv = client.get('/api/hive/install/', base_url='http://leader.example:5050')
    body = rv.get_json()
    assert 'leader.example:5050' in body['one_liners']['linux_macos']
    assert 'leader.example:5050' in body['one_liners']['windows']
