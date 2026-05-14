from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sync_grok_pot_money_maker import PROJECT_ID, sync


def test_sync_grok_pot_money_maker_is_idempotent(tmp_path):
    db_path = tmp_path / "swarm_memory.db"

    first = sync(db_path)
    second = sync(db_path)

    assert first["projects"] == 1
    assert first["steps"] == 7
    assert first["notes"] == 3
    assert first["docs"] >= 3
    assert second == {"projects": 0, "steps": 0, "notes": 0, "docs": 0}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        project = conn.execute(
            "SELECT name, priority, tags FROM projects WHERE project_id=?",
            (PROJECT_ID,),
        ).fetchone()
        steps = conn.execute(
            "SELECT title, status, owner_route FROM project_steps "
            "WHERE project_id=? ORDER BY order_idx",
            (PROJECT_ID,),
        ).fetchall()
        docs = conn.execute(
            "SELECT doc_name FROM project_docs WHERE tags LIKE ? ORDER BY doc_name",
            (f"%project:{PROJECT_ID}%",),
        ).fetchall()
        notes_count = conn.execute(
            "SELECT COUNT(*) FROM project_blackboard_notes WHERE project_id=?",
            (PROJECT_ID,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert project["name"] == "Grok-Pot-Money-Maker"
    assert project["priority"] == 8
    assert "studio-git" in project["tags"]
    assert len(steps) == 7
    assert steps[0]["status"] == "done"
    assert steps[-1]["status"] == "todo"
    assert {row["owner_route"] for row in steps} == {"studio_git"}
    assert notes_count == 3
    assert any(row["doc_name"].endswith("PROJECT_PLAN.md") for row in docs)
