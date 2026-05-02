"""End-to-end tests for synth-board + video editor backends.

Covers:
- STEP-MEDIA-CENTER-SYNTH-BOARD-20260430
- STEP-MEDIA-CENTER-VIDEO-EDITOR-20260430
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
    # Use a temp DB so we don't pollute swarm_memory.db.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    monkeypatch.chdir(ROOT)
    import sys as _sys
    from frontend.terminal import create_app
    app = create_app()
    # The actual modules used by routes are 'blueprints.<name>' (see
    # frontend/terminal.py sys.path injection). Patch both that and the
    # 'frontend.blueprints.<name>' alias so writes go to the temp DB.
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


# ── Synth-board ────────────────────────────────────────────────────────

def test_synth_board_create_get_list(client):
    r = client.post('/api/media/synth-board/projects', json={
        'name': 'pad sketch',
        'graph': {
            'nodes': [
                {'id': 'osc1', 'kind': 'oscillator'},
                {'id': 'flt1', 'kind': 'filter'},
                {'id': 'out',  'kind': 'audio-out'},
            ],
            'edges': [
                {'from': 'osc1', 'to': 'flt1'},
                {'from': 'flt1', 'to': 'out'},
            ],
        },
        'tempo': 120, 'key': 'Cmin',
    })
    assert r.status_code == 201, r.get_json()
    bid = r.get_json()['board_id']
    assert bid.startswith('SBRD-')

    rg = client.get(f'/api/media/synth-board/projects/{bid}')
    assert rg.status_code == 200
    body = rg.get_json()
    assert body['ok'] and body['board']['name'] == 'pad sketch'
    assert len(body['board']['graph']['nodes']) == 3

    rl = client.get('/api/media/synth-board/projects')
    assert rl.status_code == 200 and rl.get_json()['count'] >= 1


def test_synth_board_validates_node_kind(client):
    r = client.post('/api/media/synth-board/projects', json={
        'name': 'bad',
        'graph': {'nodes': [{'id': 'x', 'kind': 'not-a-thing'}], 'edges': []},
    })
    assert r.status_code == 400


def test_synth_board_validates_edge_endpoints(client):
    r = client.post('/api/media/synth-board/projects', json={
        'name': 'bad-edge',
        'graph': {
            'nodes': [{'id': 'a', 'kind': 'oscillator'}],
            'edges': [{'from': 'a', 'to': 'ghost'}],
        },
    })
    assert r.status_code == 400


def test_synth_board_patch_creates_revision(client):
    r = client.post('/api/media/synth-board/projects', json={
        'name': 'rev-test',
        'graph': {'nodes': [{'id': 'o', 'kind': 'oscillator'}], 'edges': []},
    })
    bid = r.get_json()['board_id']
    p = client.patch(f'/api/media/synth-board/projects/{bid}', json={
        'graph': {
            'nodes': [
                {'id': 'o', 'kind': 'oscillator'},
                {'id': 'g', 'kind': 'gain'},
            ],
            'edges': [{'from': 'o', 'to': 'g'}],
        },
        'agent': 'mistral',
    })
    assert p.status_code == 200
    rv = client.get(f'/api/media/synth-board/projects/{bid}/revisions')
    assert rv.status_code == 200 and rv.get_json()['count'] == 1


# ── Video editor ───────────────────────────────────────────────────────

def test_video_timeline_create_get_list(client):
    r = client.post('/api/media/video/timelines', json={
        'name': 'opener',
        'project_id': 'P-TEST',
        'duration_seconds': 30,
        'fps': 24,
        'resolution': '1920x1080',
        'timeline': {
            'tracks': [
                {'kind': 'video', 'clips': [
                    {'start': 0, 'end': 10, 'asset': 'clip1.mp4'},
                    {'start': 10, 'end': 20, 'asset': 'clip2.mp4'},
                ]},
                {'kind': 'audio', 'clips': [{'start': 0, 'end': 30, 'asset': 'bg.wav'}]},
            ],
        },
    })
    assert r.status_code == 201, r.get_json()
    tid = r.get_json()['timeline_id']
    assert tid.startswith('VTL-')

    g = client.get(f'/api/media/video/timelines/{tid}')
    assert g.status_code == 200
    body = g.get_json()
    assert body['timeline']['fps'] == 24
    assert len(body['timeline']['timeline']['tracks']) == 2

    lp = client.get('/api/media/video/timelines?project_id=P-TEST')
    assert lp.status_code == 200 and lp.get_json()['count'] >= 1


def test_video_timeline_rejects_bad_clip(client):
    r = client.post('/api/media/video/timelines', json={
        'name': 'bad',
        'timeline': {'tracks': [
            {'kind': 'video', 'clips': [{'start': 5, 'end': 1}]},  # end < start
        ]},
    })
    assert r.status_code == 400


def test_video_timeline_rejects_unknown_track_kind(client):
    r = client.post('/api/media/video/timelines', json={
        'name': 'bad',
        'timeline': {'tracks': [{'kind': 'lazer', 'clips': []}]},
    })
    assert r.status_code == 400


def test_video_render_records_row(client):
    r = client.post('/api/media/video/timelines', json={
        'name': 'render-test',
        'timeline': {'tracks': []},
    })
    tid = r.get_json()['timeline_id']
    rd = client.post(f'/api/media/video/timelines/{tid}/render', json={'agent': 'ghost'})
    assert rd.status_code in (201, 202)
    body = rd.get_json()
    assert body['render_id'].startswith('VREN-')
    rl = client.get(f'/api/media/video/timelines/{tid}/renders')
    assert rl.status_code == 200 and rl.get_json()['count'] == 1
