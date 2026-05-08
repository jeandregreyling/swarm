"""Y.50 — Proactive bug fixes in App Center surfaced during code review.

Three bugs found by reading the Y.47 module:

1. Building an `archived` project was silently accepted — wastes a build slot
   and makes archive status meaningless for builds. Now returns 409.
2. `GET /api/app-center/projects/<id>/builds?target=` accepted any string and
   silently returned an empty list when the user typoed the target — masking
   a real error. Now returns 400 if the target is not in `_VALID_TARGETS`.
3. `PATCH /api/app-center/builds/<id>` would crash with AttributeError if any
   field was sent as a non-string (e.g. `{"status": 123}`) because it called
   `.strip()` directly. Now type-checks before calling `.strip()` and returns
   a clean 400.

These tests lock the new contracts.
"""
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
    import sys as _sys
    from frontend.terminal import create_app
    app = create_app()
    for mod_name in ('blueprints.app_center', 'frontend.blueprints.app_center'):
        if mod_name in _sys.modules:
            monkeypatch.setattr(_sys.modules[mod_name], '_DB_PATH', tmp.name, raising=False)
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _make_project(client, **overrides):
    payload = {
        'name': 'Y50App', 'kind': 'mobile', 'framework': 'flutter',
        'targets': ['ios', 'android'],
    }
    payload.update(overrides)
    r = client.post('/api/app-center/projects', json=payload)
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()['project_id']


def test_build_rejected_on_archived_project(client):
    pid = _make_project(client)
    p = client.patch(f'/api/app-center/projects/{pid}', json={'status': 'archived'})
    assert p.status_code == 200
    r = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    assert r.status_code == 409
    body = r.get_json()
    assert body['ok'] is False
    assert 'archive' in body['error'].lower()


def test_build_allowed_on_active_paused_draft(client):
    """Sanity: only 'archived' should block builds — not draft/active/paused."""
    for status in ('draft', 'active', 'paused'):
        pid = _make_project(client, name=f'app-{status}')
        if status != 'draft':
            client.patch(f'/api/app-center/projects/{pid}', json={'status': status})
        r = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
        assert r.status_code == 201, f'status={status} got {r.status_code}: {r.get_data(as_text=True)}'


def test_list_builds_rejects_invalid_target(client):
    pid = _make_project(client)
    r = client.get(f'/api/app-center/projects/{pid}/builds?target=gameboy')
    assert r.status_code == 400
    assert 'invalid target' in r.get_json()['error'].lower()


def test_list_builds_accepts_valid_target_filter(client):
    pid = _make_project(client)
    client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    r = client.get(f'/api/app-center/projects/{pid}/builds?target=ios')
    assert r.status_code == 200
    body = r.get_json()
    assert body['count'] == 1


def test_list_builds_no_filter_returns_all(client):
    pid = _make_project(client)
    client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'android'})
    r = client.get(f'/api/app-center/projects/{pid}/builds')
    assert r.status_code == 200
    assert r.get_json()['count'] == 2


def test_patch_build_rejects_non_string_status(client):
    pid = _make_project(client)
    b = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    bid = b.get_json()['build_id']
    r = client.patch(f'/api/app-center/builds/{bid}', json={'status': 123})
    assert r.status_code == 400
    assert 'string' in r.get_json()['error'].lower()


def test_patch_build_rejects_non_string_asset_id(client):
    pid = _make_project(client)
    b = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    bid = b.get_json()['build_id']
    r = client.patch(f'/api/app-center/builds/{bid}', json={'asset_id': {'oops': 1}})
    assert r.status_code == 400


def test_patch_build_rejects_huge_asset_id(client):
    pid = _make_project(client)
    b = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    bid = b.get_json()['build_id']
    r = client.patch(f'/api/app-center/builds/{bid}', json={'asset_id': 'x' * 500})
    assert r.status_code == 400


def test_patch_build_still_accepts_valid_strings(client):
    """Regression guard for Y.47 happy path."""
    pid = _make_project(client)
    b = client.post(f'/api/app-center/projects/{pid}/build', json={'target': 'ios'})
    bid = b.get_json()['build_id']
    r = client.patch(f'/api/app-center/builds/{bid}', json={
        'status': 'succeeded', 'asset_id': 'ipa-v1.ipa',
    })
    assert r.status_code == 200
