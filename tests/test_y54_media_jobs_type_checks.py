"""Y.54 — media_jobs type-check gaps.

The central media-job submission/update endpoints had the same Y.50-class
bug: ``(data.get('x') or '').strip().lower()`` crashed with AttributeError
when callers sent non-string fields. This is the queue-handoff blueprint
used by app_center, video_editor, etc., so it's high-impact.
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


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / f"y54_{uuid.uuid4().hex[:8]}.db")

    def _conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    from frontend.terminal import create_app
    app = create_app()
    import importlib
    primary = importlib.import_module('frontend.blueprints.media_jobs')
    monkeypatch.setattr(primary, 'get_connection', _conn, raising=False)
    try:
        alt = importlib.import_module('blueprints.media_jobs')
        monkeypatch.setattr(alt, 'get_connection', _conn, raising=False)
    except ImportError:
        pass
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize('field,value', [
    ('kind', 99),
    ('agent', ['ghost']),
    ('priority', 'high'),
])
def test_submit_rejects_non_typed_field(client, field, value):
    payload = {'kind': 'musicgen', field: value}
    r = client.post('/api/media/jobs', json=payload)
    assert r.status_code == 400, r.get_data(as_text=True)


def test_submit_rejects_priority_out_of_range(client):
    r = client.post('/api/media/jobs', json={'kind': 'musicgen', 'priority': 999})
    assert r.status_code == 400


@pytest.mark.parametrize('field,value', [
    ('status', 99),
    ('asset_id', ['x']),
    ('error', {'oops': 1}),
])
def test_patch_rejects_non_string_field(client, field, value):
    # Need an existing job first; submit one with stub queue (will fail with
    # 500 because intake_internal will try to talk to real queue, but the
    # row gets persisted in the failure path — perfect for the PATCH test).
    submit = client.post('/api/media/jobs', json={'kind': 'musicgen'})
    body = submit.get_json()
    job_id = body.get('job_id')
    assert job_id, body
    r = client.patch(f'/api/media/jobs/{job_id}', json={field: value})
    assert r.status_code == 400


def test_patch_caps_asset_id_length(client):
    submit = client.post('/api/media/jobs', json={'kind': 'musicgen'})
    job_id = submit.get_json()['job_id']
    r = client.patch(f'/api/media/jobs/{job_id}',
                     json={'status': 'done', 'asset_id': 'A' * 1000})
    assert r.status_code == 200
    # Cap to 256 chars
    conn = sqlite3.connect(os.environ.get('SWARM_DB_PATH', ''))  # not used
    # Verify via a fresh GET (list)
    listing = client.get('/api/media/jobs').get_json()
    job = next((j for j in listing['items'] if j['job_id'] == job_id), None)
    assert job is not None
    assert len(job.get('asset_id') or '') <= 256
