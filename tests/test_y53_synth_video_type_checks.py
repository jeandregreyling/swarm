"""Y.53 — Type-check gaps in Y.43 surfaces (synth_board / video_editor).

Same class of bug as Y.50 fixed in app_center: ``(body.get('x') or '').strip()``
crashes with AttributeError when the client sends a non-string value (e.g.
``99``). Y.53 adds explicit type-checks before unsafe ops on synth_board
create_board and video_editor create_timeline + render_timeline.
"""
from __future__ import annotations

import os
import sys
import sqlite3
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest


def _patch_db(monkeypatch, tmp_path, module_path):
    """Bind both module-import aliases to a fresh tmp DB."""
    db_path = str(tmp_path / f"y53_{uuid.uuid4().hex[:8]}.db")

    def _conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    from frontend.terminal import create_app
    app = create_app()
    import importlib
    primary = importlib.import_module(module_path)
    monkeypatch.setattr(primary, '_conn', _conn, raising=False)
    try:
        alt = importlib.import_module(module_path.replace('frontend.', '', 1))
        monkeypatch.setattr(alt, '_conn', _conn, raising=False)
    except ImportError:
        pass
    return app


@pytest.fixture
def synth_client(tmp_path, monkeypatch):
    app = _patch_db(monkeypatch, tmp_path, 'frontend.blueprints.synth_board')
    with app.test_client() as c:
        yield c


@pytest.fixture
def video_client(tmp_path, monkeypatch):
    app = _patch_db(monkeypatch, tmp_path, 'frontend.blueprints.video_editor')
    with app.test_client() as c:
        yield c


# ── synth_board ────────────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('name', 99),
    ('owner', ['ghost']),
    ('key', {'a': 1}),
    ('notes', 7.5),
])
def test_synth_create_rejects_non_string_field(synth_client, field, value):
    r = synth_client.post('/api/media/synth-board/projects',
                          json={'name': 'ok name', field: value})
    assert r.status_code == 400, r.get_data(as_text=True)
    assert field in r.get_json()['error']


def test_synth_create_rejects_non_numeric_tempo(synth_client):
    r = synth_client.post('/api/media/synth-board/projects',
                          json={'name': 'ok', 'tempo': 'fast'})
    assert r.status_code == 400


def test_synth_create_rejects_out_of_range_tempo(synth_client):
    r = synth_client.post('/api/media/synth-board/projects',
                          json={'name': 'ok', 'tempo': 9999})
    assert r.status_code == 400


def test_synth_create_happy_path_still_works(synth_client):
    r = synth_client.post('/api/media/synth-board/projects',
                          json={'name': 'lead', 'tempo': 120})
    assert r.status_code == 201
    assert r.get_json()['ok'] is True


# ── video_editor ───────────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('name', 99),
    ('owner', 1),
    ('project_id', []),
    ('resolution', {}),
    ('notes', False),  # bool isinstance int but accepted as non-str → caught
])
def test_video_create_rejects_non_string_field(video_client, field, value):
    payload = {'name': 'ok name'}
    payload[field] = value
    r = video_client.post('/api/media/video/timelines', json=payload)
    assert r.status_code == 400, r.get_data(as_text=True)


@pytest.mark.parametrize('field,value', [
    ('duration_seconds', 'long'),
    ('fps', 'fast'),
    ('duration_seconds', -1),
    ('fps', -10),
])
def test_video_create_rejects_bad_numeric(video_client, field, value):
    payload = {'name': 'ok', field: value}
    r = video_client.post('/api/media/video/timelines', json=payload)
    assert r.status_code == 400


def test_video_create_happy_path(video_client):
    r = video_client.post('/api/media/video/timelines',
                          json={'name': 'cut1', 'fps': 24, 'duration_seconds': 12.5})
    assert r.status_code == 201


def test_video_render_rejects_non_string_agent(video_client):
    create = video_client.post('/api/media/video/timelines', json={'name': 'cut'})
    tid = create.get_json()['timeline_id']
    r = video_client.post(f'/api/media/video/timelines/{tid}/render',
                          json={'agent': 99})
    assert r.status_code == 400
