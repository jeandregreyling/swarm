"""Y.52 — /api/interests cross-user isolation.

Bug discovered after Y.48 KC seed: ``/api/interests?username=X`` ignored
the username filter on the saved_interests query. After seeding 37
score-8 rows for user 'seven', they evicted lower-scored rows for other
users from the LIMIT-30 window, breaking test_interests_wiring on a
clean DB.

Fix: filter by ``WHERE username = ?`` in the saved_interests SQL. This
test pins the contract.
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
def isolated_db(tmp_path, monkeypatch):
    """Spin up a temp DB so we don't pollute swarm_memory.db."""
    db_path = str(tmp_path / f"interests_{uuid.uuid4().hex[:8]}.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY, content TEXT, message_type TEXT,
            from_agent TEXT, created_at TEXT
        );
        CREATE TABLE queue (
            id INTEGER PRIMARY KEY, question TEXT, subject TEXT,
            source_type TEXT, created_at TEXT
        );
        CREATE TABLE memory (id INTEGER PRIMARY KEY, tags TEXT);
        CREATE TABLE sniffer_memory (
            id INTEGER PRIMARY KEY, description TEXT, occurrence_count INTEGER
        );
        CREATE TABLE user_interests (
            id INTEGER PRIMARY KEY,
            username TEXT, topic TEXT, category TEXT,
            source TEXT, source_agent TEXT, score REAL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, topic)
        );
        """
    )
    # Seed 35 high-score rows for 'seven' (mimics Y.48 seed) +
    # one low-score row for 'ghost'. Without the username filter the
    # ghost row would be evicted by the LIMIT 30.
    for i in range(35):
        conn.execute(
            "INSERT INTO user_interests (username, topic, category, source, score, active) "
            "VALUES (?, ?, 'media', 'librarian', 8.0, 1)",
            ('seven', f'topic_seven_{i}'),
        )
    conn.execute(
        "INSERT INTO user_interests (username, topic, category, source, score, active) "
        "VALUES ('ghost', 'ghost_only_topic', 'test', 'agent', 1.0, 1)"
    )
    conn.commit()
    conn.close()

    # Patch every connection-providing module path the route may import.
    def _conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    # Force the running app onto our DB
    monkeypatch.setenv('SWARM_DB_PATH', db_path)
    # Patch get_connection on every alias so blueprint-side imports hit ours
    from frontend.terminal import create_app
    app = create_app()
    import frontend.blueprints.interests_bp as ibp
    monkeypatch.setattr(ibp, 'get_connection', _conn)
    try:
        import blueprints.interests_bp as ibp2
        monkeypatch.setattr(ibp2, 'get_connection', _conn)
    except ImportError:
        pass

    with app.test_client() as client:
        yield client


def test_ghost_query_only_returns_ghost_rows(isolated_db):
    r = isolated_db.get('/api/interests?username=ghost')
    assert r.status_code == 200
    saved = r.get_json().get('saved_interests') or []
    topics = [row['topic'] for row in saved]
    # ghost has exactly 1 saved row; LIMIT 30 must not let seven's rows leak in
    assert 'ghost_only_topic' in topics
    seven_leaks = [t for t in topics if t.startswith('topic_seven_')]
    assert seven_leaks == [], f'cross-user leak: {seven_leaks}'


def test_seven_query_only_returns_seven_rows(isolated_db):
    r = isolated_db.get('/api/interests?username=seven')
    saved = r.get_json().get('saved_interests') or []
    topics = [row['topic'] for row in saved]
    assert 'ghost_only_topic' not in topics
    assert any(t.startswith('topic_seven_') for t in topics)


def test_default_username_is_seven(isolated_db):
    """Frontend calls /api/interests with no username — must default to seven
    (matches Y.48 seed) and not leak ghost rows."""
    r = isolated_db.get('/api/interests')
    saved = r.get_json().get('saved_interests') or []
    topics = [row['topic'] for row in saved]
    assert 'ghost_only_topic' not in topics
