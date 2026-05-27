import sqlite3
import sys
from pathlib import Path

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "frontend"))
from frontend.blueprints import docs as docs_bp_module


def _client(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm_memory.db"

    def get_connection():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE IF NOT EXISTS project_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                tags TEXT DEFAULT 'all'
            )"""
        )
        return conn

    monkeypatch.setattr(docs_bp_module, "_SWARM_ROOT", str(tmp_path))
    monkeypatch.setattr(docs_bp_module, "get_connection", get_connection)
    monkeypatch.setattr(docs_bp_module, "log_activity", lambda *a, **k: None)

    app = Flask(__name__)
    app.register_blueprint(docs_bp_module.docs_bp)
    return app.test_client(), db_path


def test_recursive_chunk_rejects_paths_outside_swarm_root(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    res = client.post("/api/docs/recursive-chunk", json={"query": "needle", "path": "/tmp"})

    assert res.status_code == 400
    assert res.get_json()["error"] == "path must stay inside swarm root"


def test_recursive_chunk_uses_rg_and_writes_kc_docs(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    target = tmp_path / "docs" / "note.md"
    target.write_text(
        "alpha\nneedle appears here\nomega\n\nneedle appears again\n",
        encoding="utf-8",
    )
    client, db_path = _client(tmp_path, monkeypatch)

    res = client.post(
        "/api/docs/recursive-chunk",
        json={"query": "needle", "path": "docs", "limit": 4},
    )

    body = res.get_json()
    assert res.status_code == 200
    assert body["ok"] is True
    assert body["found"] >= 1
    assert body["blackboard_ids"][0].startswith("[Recursive] needle")

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT doc_name, content, tags FROM project_docs").fetchone()
    assert row is not None
    assert "needle appears here" in row[1]
    assert "recursive-search" in row[2]
