"""Y.47 — App Center backend e2e tests."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    monkeypatch.chdir(ROOT)
    # The running app imports blueprints via importlib as 'blueprints.<name>'
    # (see frontend/terminal.py adding frontend/ to sys.path). Importing as
    # 'frontend.blueprints.<name>' creates a SECOND module object — patching
    # only that one leaves the actual route handler reading the unpatched
    # _DB_PATH and writing to the real swarm_memory.db. We patch both.
    import sys as _sys
    from frontend.terminal import create_app
    app = create_app()  # ensures blueprints.<name> are loaded into sys.modules
    for mod_name in ('blueprints.app_center', 'blueprints.synth_board',
                     'blueprints.video_editor'):
        if mod_name in _sys.modules:
            monkeypatch.setattr(_sys.modules[mod_name], '_DB_PATH', tmp.name)
    # Defensive: also patch the frontend.blueprints.* aliases in case something
    # imports through that path.
    from frontend.blueprints import app_center, synth_board, video_editor
    monkeypatch.setattr(app_center, '_DB_PATH', tmp.name)
    monkeypatch.setattr(synth_board, '_DB_PATH', tmp.name)
    monkeypatch.setattr(video_editor, '_DB_PATH', tmp.name)
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_registry_lists_contract(client):
    r = client.get('/api/app-center/registry').get_json()
    assert r['ok']
    assert 'mobile' in r['kinds'] and 'tablet' in r['kinds'] and 'game' in r['kinds']
    assert 'flutter' in r['frameworks'] and 'godot' in r['frameworks']
    assert 'ios' in r['targets'] and 'wasm' in r['targets']


def test_create_project_validates_kind(client):
    r = client.post('/api/app-center/projects', json={
        'name': 'BadKind', 'kind': 'spaceship', 'framework': 'flutter',
    })
    assert r.status_code == 400


def test_create_project_validates_framework(client):
    r = client.post('/api/app-center/projects', json={
        'name': 'BadFW', 'kind': 'mobile', 'framework': 'cobol',
    })
    assert r.status_code == 400


def test_create_project_validates_targets(client):
    r = client.post('/api/app-center/projects', json={
        'name': 'BadTarget', 'kind': 'game', 'framework': 'godot',
        'targets': ['ios', 'gameboy'],
    })
    assert r.status_code == 400


def test_full_lifecycle(client):
    r = client.post('/api/app-center/projects', json={
        'name': 'Mirror Dash',
        'kind': 'game',
        'framework': 'godot',
        'targets': ['windows', 'macos', 'linux', 'web'],
        'description': 'top-down arcade',
        'tags': ['arcade', 'pixel-art'],
        'studio_project_id': 'P-MIRROR',
    })
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()['project_id']
    assert pid.startswith('APP-')

    g = client.get(f'/api/app-center/projects/{pid}').get_json()
    assert g['ok']
    assert g['project']['name'] == 'Mirror Dash'
    assert g['project']['kind'] == 'game'
    assert g['project']['tags'] == ['arcade', 'pixel-art']
    assert {t['target'] for t in g['project']['targets']} == {'windows', 'macos', 'linux', 'web'}

    # add a new target
    add = client.post(f'/api/app-center/projects/{pid}/targets', json={'target': 'wasm'})
    assert add.status_code == 201
    # duplicate target → 409
    dup = client.post(f'/api/app-center/projects/{pid}/targets', json={'target': 'wasm'})
    assert dup.status_code == 409

    # PATCH name + status + tags
    p = client.patch(f'/api/app-center/projects/{pid}', json={
        'name': 'Mirror Dash 2', 'status': 'active', 'tags': ['arcade', 'pixel-art', 'roguelike'],
    })
    assert p.status_code == 200
    g2 = client.get(f'/api/app-center/projects/{pid}').get_json()
    assert g2['project']['name'] == 'Mirror Dash 2'
    assert g2['project']['status'] == 'active'

    # invalid PATCH (bad framework)
    bad = client.patch(f'/api/app-center/projects/{pid}', json={'framework': 'cobol'})
    assert bad.status_code == 400


def test_build_succeeds_then_lists(client):
    pid = client.post('/api/app-center/projects', json={
        'name': 'TestApp', 'kind': 'mobile', 'framework': 'flutter',
        'targets': ['ios', 'android'],
    }).get_json()['project_id']
    b = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'android'})
    assert b.status_code == 201, b.get_json()
    bid = b.get_json()['build_id']
    assert bid.startswith('BUILD-')
    assert b.get_json()['status'] == 'queued'

    # PATCH build → succeeded
    p = client.patch(f'/api/app-center/builds/{bid}', json={
        'status': 'succeeded', 'asset_id': 'apk-v1.apk',
    })
    assert p.status_code == 200
    bl = client.get(f'/api/app-center/projects/{pid}/builds').get_json()
    assert bl['count'] == 1 and bl['builds'][0]['status'] == 'succeeded'

    # target row reflects status
    g = client.get(f'/api/app-center/projects/{pid}').get_json()
    android = next(t for t in g['project']['targets'] if t['target'] == 'android')
    assert android['status'] == 'succeeded'
    assert android['last_build_id'] == bid


def test_build_rejects_unattached_target(client):
    pid = client.post('/api/app-center/projects', json={
        'name': 'X', 'kind': 'desktop', 'framework': 'tauri',
        'targets': ['windows'],
    }).get_json()['project_id']
    r = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    assert r.status_code == 400


def test_build_failure_returns_5xx(client, monkeypatch):
    pid = client.post('/api/app-center/projects', json={
        'name': 'FailApp', 'kind': 'web', 'framework': 'next',
        'targets': ['web'],
    }).get_json()['project_id']
    import core.pipeline.queue_manager as qm
    monkeypatch.setattr(qm, 'intake_internal', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('queue offline')))
    r = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'web'})
    assert r.status_code >= 500
    body = r.get_json()
    assert body['ok'] is False
    assert body['status'] == 'failed'
    # row still recorded
    bl = client.get(f'/api/app-center/projects/{pid}/builds').get_json()
    assert bl['count'] == 1 and bl['builds'][0]['status'] == 'failed'


def test_list_projects_filters(client):
    for kind, fw in [('mobile', 'flutter'), ('game', 'godot'), ('desktop', 'tauri')]:
        client.post('/api/app-center/projects', json={
            'name': f'P-{kind}', 'kind': kind, 'framework': fw, 'targets': [],
        })
    games = client.get('/api/app-center/projects?kind=game').get_json()
    assert games['count'] == 1 and games['projects'][0]['kind'] == 'game'
    flutter = client.get('/api/app-center/projects?framework=flutter').get_json()
    assert flutter['count'] == 1 and flutter['projects'][0]['framework'] == 'flutter'
