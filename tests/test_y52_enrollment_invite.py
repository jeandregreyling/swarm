"""Y.52 — /api/enrollment/invite endpoint coverage.

Y.52 added the missing invite-issue endpoint that /api/enrollment/create
already consumed (it only accepted invite tokens but no endpoint produced
them). This test pins the contract and the validation behaviour.
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
    db_path = str(tmp_path / f"enroll_{uuid.uuid4().hex[:8]}.db")
    # Pre-create user_profiles + owner so /invite is allowed
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE user_profiles (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            display_name TEXT,
            email TEXT,
            role TEXT,
            password_hash TEXT,
            approved INTEGER,
            is_active INTEGER,
            created_at REAL
        );
        INSERT INTO user_profiles (username, role, approved, is_active, created_at)
        VALUES ('seven', 'owner', 1, 1, 0);
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv('SWARM_DB', db_path)
    from frontend.terminal import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_invite_post_creates_token(client):
    r = client.post('/api/enrollment/invite', json={'role': 'assistant'})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body['ok'] and body['role'] == 'assistant'
    assert isinstance(body['token'], str) and len(body['token']) >= 16


def test_invite_get_lists_open_tokens(client):
    client.post('/api/enrollment/invite', json={'role': 'co_owner', 'email': 'a@b.co'})
    client.post('/api/enrollment/invite', json={'role': 'member'})
    r = client.get('/api/enrollment/invite')
    body = r.get_json()
    assert body['ok'] and body['count'] >= 2
    roles = [i['role'] for i in body['invites']]
    assert 'co_owner' in roles and 'member' in roles


def test_invite_rejects_unknown_role(client):
    r = client.post('/api/enrollment/invite', json={'role': 'god_mode'})
    assert r.status_code == 400


def test_invite_rejects_non_string_role(client):
    r = client.post('/api/enrollment/invite', json={'role': 99})
    assert r.status_code == 400


def test_invite_rejects_bad_email(client):
    r = client.post('/api/enrollment/invite', json={'role': 'member', 'email': 'no-at-sign'})
    assert r.status_code == 400


def test_invite_token_is_consumable_by_create(client):
    """End-to-end: issue invite → create account with it → second create fails."""
    inv = client.post('/api/enrollment/invite', json={'role': 'assistant'}).get_json()
    token = inv['token']
    r = client.post('/api/enrollment/create', json={
        'username': 'helper',
        'password': 'hunter2hunter2',
        'invite': token,
        'role': 'assistant',
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    # Second use must fail (consumed)
    r2 = client.post('/api/enrollment/create', json={
        'username': 'helper2',
        'password': 'hunter2hunter2',
        'invite': token,
        'role': 'assistant',
    })
    assert r2.status_code == 403


def test_invite_blocked_without_owner(tmp_path, monkeypatch):
    """Without owner_profiles row, POST /invite must 409."""
    db_path = str(tmp_path / f"enroll_no_owner_{uuid.uuid4().hex[:8]}.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE user_profiles (
            id INTEGER PRIMARY KEY, username TEXT UNIQUE, display_name TEXT,
            email TEXT, role TEXT, password_hash TEXT, approved INTEGER,
            is_active INTEGER, created_at REAL
        );
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv('SWARM_DB', db_path)
    from frontend.terminal import create_app
    app = create_app()
    with app.test_client() as c:
        r = c.post('/api/enrollment/invite', json={'role': 'assistant'})
    assert r.status_code == 409
