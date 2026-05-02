"""Y.45 — PATCH validation hardening for synth-board + video-editor.

Locks the new typed validation in PATCH endpoints so future regressions
that re-loosen the contract fail CI.
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
    for mod_name in ('blueprints.synth_board', 'blueprints.video_editor'):
        if mod_name in _sys.modules:
            monkeypatch.setattr(_sys.modules[mod_name], '_DB_PATH', tmp.name)
    from frontend.blueprints import synth_board, video_editor
    monkeypatch.setattr(synth_board, '_DB_PATH', tmp.name)
    monkeypatch.setattr(video_editor, '_DB_PATH', tmp.name)
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


# ── synth_board PATCH validation ───────────────────────────────────────

def _make_board(client, **overrides):
    body = {'name': 'base', 'graph': {'nodes': [], 'edges': []}}
    body.update(overrides)
    r = client.post('/api/media/synth-board/projects', json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['board_id']


def test_synth_patch_rejects_non_numeric_tempo(client):
    bid = _make_board(client)
    r = client.patch(f'/api/media/synth-board/projects/{bid}', json={'tempo': 'fast'})
    assert r.status_code == 400
    assert 'tempo' in r.get_json()['error']


def test_synth_patch_rejects_empty_name(client):
    bid = _make_board(client)
    r = client.patch(f'/api/media/synth-board/projects/{bid}', json={'name': '   '})
    assert r.status_code == 400


def test_synth_patch_rejects_non_string_notes(client):
    bid = _make_board(client)
    r = client.patch(f'/api/media/synth-board/projects/{bid}', json={'notes': 42})
    assert r.status_code == 400


def test_synth_patch_accepts_valid_scalar_update(client):
    bid = _make_board(client)
    r = client.patch(f'/api/media/synth-board/projects/{bid}', json={
        'name': 'renamed', 'tempo': 90.5, 'key': 'Gmaj', 'notes': 'updated',
    })
    assert r.status_code == 200, r.get_json()
    g = client.get(f'/api/media/synth-board/projects/{bid}').get_json()
    assert g['board']['name'] == 'renamed'
    assert g['board']['tempo'] == 90.5
    assert g['board']['key'] == 'Gmaj'


def test_synth_patch_rejects_out_of_range_tempo(client):
    bid = _make_board(client)
    r = client.patch(f'/api/media/synth-board/projects/{bid}', json={'tempo': 9999})
    assert r.status_code == 400


# ── video_editor PATCH validation ──────────────────────────────────────

def _make_timeline(client):
    r = client.post('/api/media/video/timelines', json={
        'name': 'base', 'timeline': {'tracks': []},
    })
    assert r.status_code == 201
    return r.get_json()['timeline_id']


def test_video_patch_rejects_non_numeric_fps(client):
    tid = _make_timeline(client)
    r = client.patch(f'/api/media/video/timelines/{tid}', json={'fps': '24fps'})
    assert r.status_code == 400


def test_video_patch_rejects_negative_duration(client):
    tid = _make_timeline(client)
    r = client.patch(f'/api/media/video/timelines/{tid}', json={'duration_seconds': -5})
    assert r.status_code == 400


def test_video_patch_rejects_empty_name(client):
    tid = _make_timeline(client)
    r = client.patch(f'/api/media/video/timelines/{tid}', json={'name': ''})
    assert r.status_code == 400


def test_video_patch_accepts_valid_scalar_update(client):
    tid = _make_timeline(client)
    r = client.patch(f'/api/media/video/timelines/{tid}', json={
        'name': 'renamed',
        'fps': 30,
        'duration_seconds': 60,
        'resolution': '3840x2160',
        'project_id': 'P-NEW',
    })
    assert r.status_code == 200
    g = client.get(f'/api/media/video/timelines/{tid}').get_json()
    assert g['timeline']['name'] == 'renamed'
    assert g['timeline']['fps'] == 30
