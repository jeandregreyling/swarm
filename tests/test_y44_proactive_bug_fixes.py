"""Regressions for proactive bug-hunt batch Y.44.

Locks three bug-fixes against the recently shipped surfaces:

1. ``DELETE /api/kc/media/curriculum/<id>`` must 404 on missing rows
   instead of silently returning ``{ok: true}``.
2. ``POST /api/kc/media/curriculum`` must only treat the unique-conflict
   case as a merge; other DB errors must surface, not be re-written as
   "merged".
3. ``POST /api/media/video/timelines/<id>/render`` must return HTTP 5xx
   when the queue intake fails, not HTTP 202 ("Accepted") which would
   mislead clients into thinking work is in progress.
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
def app_client(monkeypatch):
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
        yield app, c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_delete_curriculum_unknown_row_returns_404(app_client):
    _app, client = app_client
    r = client.delete('/api/kc/media/curriculum/999999')
    assert r.status_code == 404, r.get_json()
    body = r.get_json()
    assert body['ok'] is False
    assert 'not found' in body.get('error', '').lower()


def test_delete_curriculum_existing_row_returns_count(app_client):
    _app, client = app_client
    import uuid
    topic = f'lo-fi-beats-{uuid.uuid4().hex[:8]}'
    add = client.post('/api/kc/media/curriculum', json={
        'topic': topic,
        'kind': 'music',
        'tool': 'musicgen',
        'notes': 'baseline',
    })
    assert add.status_code == 200
    listing = client.get('/api/kc/media/curriculum?kind=music').get_json()
    new = next(r for r in listing['items'] if r['topic'] == topic)
    rid = new['id']
    d = client.delete(f'/api/kc/media/curriculum/{rid}')
    assert d.status_code == 200
    assert d.get_json()['deleted'] == 1
    d2 = client.delete(f'/api/kc/media/curriculum/{rid}')
    assert d2.status_code == 404


def test_add_curriculum_only_catches_integrity_error(app_client):
    """The merge path must not swallow non-IntegrityError exceptions."""
    import inspect

    from frontend.blueprints import media_curriculum as mc

    src = inspect.getsource(mc.add_curriculum)
    # Must NOT bare-except.
    assert 'except Exception' not in src, \
        'add_curriculum must narrow except to IntegrityError so unrelated errors surface.'
    assert 'sqlite3.IntegrityError' in src, \
        'add_curriculum must explicitly catch sqlite3.IntegrityError on the merge path.'


def test_add_curriculum_merge_path_works(app_client):
    """Adding the same (topic, kind, tool) twice must merge notes via the IntegrityError branch."""
    _app, client = app_client
    import uuid
    topic = f'cinematic-strings-{uuid.uuid4().hex[:8]}'
    a = client.post('/api/kc/media/curriculum', json={
        'topic': topic, 'kind': 'music', 'tool': 'audio_ldm', 'notes': 'first',
    })
    assert a.status_code == 200 and a.get_json()['merged'] is False
    b = client.post('/api/kc/media/curriculum', json={
        'topic': topic, 'kind': 'music', 'tool': 'audio_ldm', 'notes': 'second',
    })
    assert b.status_code == 200 and b.get_json()['merged'] is True
    listing = client.get('/api/kc/media/curriculum?kind=music').get_json()
    rows = [r for r in listing['items'] if r['topic'] == topic]
    assert len(rows) == 1
    assert rows[0]['notes'] == 'second'


def test_video_render_failure_returns_5xx(app_client, monkeypatch):
    """When intake_internal blows up, render must NOT return 202."""
    _app, client = app_client
    # Create a real timeline first.
    r = client.post('/api/media/video/timelines', json={'name': 'r', 'timeline': {'tracks': []}})
    tid = r.get_json()['timeline_id']

    # Force the queue intake to raise so we hit the failure branch.
    import core.pipeline.queue_manager as qm
    def boom(*a, **k):
        raise RuntimeError('queue offline')
    monkeypatch.setattr(qm, 'intake_internal', boom)

    rd = client.post(f'/api/media/video/timelines/{tid}/render', json={})
    assert rd.status_code >= 500, f'expected 5xx on intake failure, got {rd.status_code}'
    body = rd.get_json()
    assert body['ok'] is False
    assert body['status'] == 'failed'
    assert 'queue offline' in (body.get('error') or '')

    # The render row must still be persisted so the UI can see the failure.
    rl = client.get(f'/api/media/video/timelines/{tid}/renders').get_json()
    assert rl['count'] == 1
    assert rl['renders'][0]['status'] == 'failed'
