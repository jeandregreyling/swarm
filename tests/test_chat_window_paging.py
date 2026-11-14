"""Owner 13 Nov (practice 16, APEX): main chat loads the latest messages first and older ones on scroll-up.
GET /api/conversations/<id>/messages?limit=N returns the newest N in order; &before=ID the N before that message; has_more says
whether older ones exist. Without limit the endpoint is unchanged (all messages)."""
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask


@pytest.fixture
def client(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'frontend'))
    from frontend.blueprints import conversations
    db = sqlite3.connect(':memory:', check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE conversations(id INTEGER PRIMARY KEY, title TEXT, source TEXT, created_at TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT,
                              message_type TEXT, tokens_used INT, created_at TEXT);
        CREATE TABLE chat_jobs(job_id TEXT, conversation_id INT, agent TEXT, status TEXT, runtime_class TEXT, stage TEXT,
                               eta_seconds INT, elapsed_ms INT, tokens INT, error TEXT, stage_trace_json TEXT, started_at REAL, updated_at REAL);
        INSERT INTO conversations VALUES(7, 'Main', 'web', '2026-11-13');
    """)
    db.executemany("INSERT INTO messages(id,conversation_id,from_agent,content,message_type) VALUES(?,7,'user',?,'user')",
                   [(i, f'message {i}') for i in range(1, 46)])
    class Keep:                       # the endpoint closes its connection; keep the in-memory one alive
        def __getattr__(self, name):
            return getattr(db, name)

        def close(self):
            pass
    monkeypatch.setattr(conversations, 'get_connection', lambda: Keep())
    from core import hb_workflow, hb_tasks
    monkeypatch.setattr(hb_workflow, 'visible_jobs', lambda conn, conv_id: [])
    monkeypatch.setattr(hb_tasks, 'enrich', lambda conn, rows: rows)
    app = Flask('paging-test'); app.register_blueprint(conversations.conversations_bp)
    return app.test_client()


def test_practice_16_latest_messages_first(client):
    data = client.get('/api/conversations/7/messages?limit=20').get_json()
    assert [m['id'] for m in data['messages']] == list(range(26, 46)) and data['has_more'] is True


def test_practice_16_older_messages_before_an_id(client):
    data = client.get('/api/conversations/7/messages?limit=20&before=26').get_json()
    assert [m['id'] for m in data['messages']] == list(range(6, 26)) and data['has_more'] is True
    data = client.get('/api/conversations/7/messages?limit=20&before=6').get_json()
    assert [m['id'] for m in data['messages']] == [1, 2, 3, 4, 5] and data['has_more'] is False


def test_practice_16_without_limit_nothing_changes(client):
    data = client.get('/api/conversations/7/messages').get_json()
    assert len(data['messages']) == 45 and data.get('has_more', False) is False
