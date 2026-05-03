"""Y.56 — Type-check sweep continued: enrollment/proposals/nine.

These three top-level surfaces also crashed with AttributeError on
non-string JSON values (Y.50 class). Apply the same hardening template.
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
    db = str(tmp_path / 'y56.db')
    monkeypatch.setenv('SWARM_DB', db)
    monkeypatch.setenv('SWARM_DB_PATH', db)
    from frontend.terminal import create_app
    app = create_app()
    with app.test_client() as c:
        yield c


# ── enrollment.py /create ─────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('username', 99),
    ('password', ['x']),
    ('display_name', {'a': 1}),
    ('email', 7),
    ('role', [1]),
    ('invite', {'k': 'v'}),
])
def test_enrollment_create_rejects_non_string(client, field, value):
    payload = {'username': 'newowner', 'password': 'longenoughpw',
               field: value}
    r = client.post('/api/enrollment/create', json=payload)
    assert r.status_code == 400, r.get_data(as_text=True)


# ── proposals.py /api/queue ───────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('agent', 99),
    ('title', ['t']),
])
def test_proposals_intake_rejects_non_string(client, field, value):
    payload = {'title': 'a', field: value}
    r = client.post('/api/queue', json=payload)
    assert r.status_code == 400


# ── proposals.py /notes ───────────────────────────────────────────────

def _seed_proposal(client):
    """Create a proposal so the notes endpoint has something to attach to."""
    r = client.post('/api/queue', json={'title': 'seed for note tests'})
    assert r.status_code in (200, 201)
    j = r.get_json()
    return j.get('proposal_id') or j.get('id') or 'unknown'


@pytest.mark.parametrize('field,value', [
    ('content', 99),
    ('author', ['x']),
])
def test_proposals_add_note_rejects_non_string(client, field, value):
    pid = _seed_proposal(client)
    payload = {'content': 'note', field: value}
    r = client.post(f'/api/work-proposals/{pid}/notes', json=payload)
    assert r.status_code == 400


# ── nine.py ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('value', [99, ['x'], {'a': 1}])
def test_nine_chat_rejects_non_string_message(client, value):
    r = client.post('/api/nine', json={'message': value})
    assert r.status_code == 400


@pytest.mark.parametrize('value', [99, ['x'], {'a': 1}])
def test_nine_stream_rejects_non_string_message(client, value):
    r = client.post('/api/nine/stream', json={'message': value})
    assert r.status_code == 400
