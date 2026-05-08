"""Conversation history trace payload regression tests."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]


def test_conversation_messages_include_chat_job_stage_traces(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm_memory.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setenv("SWARM_ROOT", str(ROOT))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(ROOT / "frontend") not in sys.path:
        sys.path.insert(0, str(ROOT / "frontend"))

    from utils.db import _connection
    importlib.reload(_connection)
    from utils.db import _schema
    importlib.reload(_schema)
    _schema.initialise_database()

    from utils.db._connection import get_connection

    trace = [{"text": "queued"}, {"text": "failed while loading history"}]
    with get_connection() as conn:
        conv_id = conn.execute(
            "INSERT INTO conversations (title, source) VALUES ('trace test', 'terminal-ui:TEST')"
        ).lastrowid
        conn.execute(
            """INSERT INTO messages (conversation_id, from_agent, to_agent, content, message_type)
               VALUES (?, 'user', 'gemma', 'Status update', 'chat')""",
            (conv_id,),
        )
        conn.execute(
            """INSERT INTO chat_jobs
                 (job_id, conversation_id, agent, status, runtime_class, eta_seconds,
                  started_at, updated_at, stage, error, elapsed_ms, stage_trace_json)
               VALUES (?, ?, 'gemma', 'failed', 'local', 85,
                  '2026-05-08T05:10:01Z', '2026-05-08T05:19:43Z',
                  'failed', 'history load failed', 591398, ?)""",
            ("chatjob-trace-test", conv_id, json.dumps(trace)),
        )
        conn.commit()

    from frontend.blueprints import conversations
    importlib.reload(conversations)
    monkeypatch.setattr(conversations, "get_connection", get_connection)
    app = Flask(__name__)
    app.register_blueprint(conversations.conversations_bp)
    app.config["TESTING"] = True

    resp = app.test_client().get(f"/api/conversations/{conv_id}/messages")
    body = resp.get_json()

    assert resp.status_code == 200
    assert len(body["messages"]) == 1
    assert body["jobs"][0]["job_id"] == "chatjob-trace-test"
    assert body["jobs"][0]["status"] == "failed"
    assert body["jobs"][0]["stage_trace"] == trace
