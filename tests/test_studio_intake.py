from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _connect(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            methodology TEXT DEFAULT 'mixed',
            status TEXT DEFAULT 'active',
            owner TEXT DEFAULT 'seven',
            created_at REAL NOT NULL,
            updated_at REAL
        )"""
    )
    return conn


def test_link_proposal_defaults_to_control_project(tmp_path, monkeypatch):
    from utils import studio_intake

    db_path = tmp_path / "studio.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(studio_intake, "get_connection", get_conn)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO projects
               (project_id, name, status, created_at, updated_at)
               VALUES (?, 'Control', 'active', ?, ?)""",
            (studio_intake.CONTROL_PROJECT_ID, time.time(), time.time()),
        )

    project_id = studio_intake.link_proposal_to_project(
        "PROP-1",
        title="Fix agent timeout",
        description="No explicit project id.",
    )

    assert project_id == studio_intake.CONTROL_PROJECT_ID
    with get_conn() as conn:
        row = conn.execute(
            "SELECT project_id FROM proposal_projects WHERE proposal_id='PROP-1'"
        ).fetchone()
    assert row["project_id"] == studio_intake.CONTROL_PROJECT_ID


def test_link_proposal_prefers_explicit_project_id(tmp_path, monkeypatch):
    from utils import studio_intake

    db_path = tmp_path / "studio.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(studio_intake, "get_connection", get_conn)
    with get_conn() as conn:
        now = time.time()
        conn.execute(
            """INSERT INTO projects
               (project_id, name, status, created_at, updated_at)
               VALUES (?, 'Control', 'active', ?, ?)""",
            (studio_intake.CONTROL_PROJECT_ID, now, now),
        )
        conn.execute(
            """INSERT INTO projects
               (project_id, name, status, created_at, updated_at)
               VALUES ('P-ABCDEF1234', 'Specific', 'active', ?, ?)""",
            (now, now),
        )

    project_id = studio_intake.link_proposal_to_project(
        "PROP-2",
        title="Work for P-ABCDEF1234",
        description="Should not use control project.",
    )

    assert project_id == "P-ABCDEF1234"
