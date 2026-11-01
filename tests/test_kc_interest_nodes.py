import sqlite3
import sys
from pathlib import Path

from flask import Flask
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))
from frontend.blueprints import interests_bp


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "interests.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE user_interests (
            username TEXT, topic TEXT, category TEXT DEFAULT 'general', source TEXT,
            source_agent TEXT DEFAULT '', score REAL, active INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(username, topic))""")
        conn.executemany(
            "INSERT INTO user_interests (username, topic, source, score) VALUES (?, ?, 'user', 10)",
            [("alice", f"Topic {i}") for i in range(42)] + [("bob", "Private topic")],
        )
    def connect():
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(interests_bp, "get_connection", connect)
    app = Flask(__name__)
    app.register_blueprint(interests_bp.interests_bp)
    return app.test_client()


def test_saved_nodes_are_complete_and_user_scoped(client):
    response = client.get("/api/interests?saved_only=1&username=alice")
    assert response.status_code == 200
    saved = response.json["saved_interests"]
    assert len(saved) == 42
    assert all(row["topic"] != "Private topic" for row in saved)


def test_add_remove_and_readd_persist_for_same_user(client):
    data = {"username": "alice", "topics": ["SAP HCM Australia"]}
    assert client.post("/api/interests/seed", json=data).json["saved"] == data["topics"]
    assert client.post("/api/interests/remove", json={"username": "bob", "topic": data["topics"][0]}).status_code == 200
    saved = lambda: client.get("/api/interests?saved_only=1&username=alice").json["saved_interests"]
    assert len(saved()) == 43
    client.post("/api/interests/remove", json={"username": "alice", "topic": data["topics"][0]})
    assert len(saved()) == 42
    client.post("/api/interests/seed", json=data)
    assert len(saved()) == 43
