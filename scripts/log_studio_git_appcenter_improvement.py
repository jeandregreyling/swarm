#!/usr/bin/env python3
"""Record Studio Git/App Center visibility improvements in Studio projects."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("SWARM_DB_PATH") or os.environ.get("SWARM_DB") or ROOT / "swarm_memory.db")


PROJECTS = {
    "P-00221285D1": {
        "name": "Continuous Improvement",
        "tags": ["continuous-improvement", "studio-git", "backend-to-ui"],
    },
    "P-855E64250C": {
        "name": "Grok-Pot-Money-Maker",
        "tags": ["grok-pot", "money-maker", "studio-git", "app-center"],
    },
}


STEPS = [
    (
        "S-P00221285D1-STUDIO-GIT-MIRROR",
        "P-00221285D1",
        "Studio Git mirrors online branches into DEV/UAT",
        "Add Fridays/Studio Git controls for fetch, branch dropdown, compare, checkout, pull and push so GitHub branches can be reviewed without VS Code or GitHub web.",
        "done",
    ),
    (
        "S-P00221285D1-BACKEND-UI-RULE",
        "P-00221285D1",
        "Backend-to-UI rule for system changes",
        "Every backend feature must include Flask blueprint registration, a visible UI tile/tab/route, tests, and KC/manual documentation before it counts as usable.",
        "done",
    ),
    (
        "S-P855E64250C-GROK-BOUNDARY",
        "P-855E64250C",
        "Separate Grok sandpit discovery from App Center and Studio Git",
        "Keep Grok's sandpit project-discovery idea as intake input, but do not wire sandpit Studio projects into App Center or use App Center for Git branch management.",
        "done",
    ),
]


NOTES = [
    (
        "P-00221285D1",
        "decision",
        "Backend changes are not complete until they are registered through Flask/blueprints, exposed in the UI, covered by tests, and documented in KC/manual content.",
    ),
    (
        "P-855E64250C",
        "handoff",
        "Absorbed from Grok: branch visibility requirement, sandpit project plan intake, and the need to make backend surfaces visible. Left for Grok sandpits: money bots, newsletters, and revenue/media/finance experiments.",
    ),
]


DOC_NAME = "sandpits/studio/P-00221285D1/STUDIO_GIT_APPCENTER_VISIBILITY_2026-05-09.md"
DOC_CONTENT = """# Studio Git + App Center Visibility

## Decision
Studio Git owns branch mirroring and DEV/UAT checkout/pull/push workflows.
App Center is a backend/API surface for app/game build projects, not Studio Git.

## Rule
Backend changes must be brought through Flask/blueprints, visible UI routes or tabs,
tests, and KC/manual documentation before they are considered usable.

## Grok Boundary
Grok may propose sandpit plans and experiments. Reviewed system-owned changes must
integrate through real blueprints and visible Studio/Fridays UI surfaces.
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            methodology TEXT NOT NULL DEFAULT 'mixed',
            status TEXT NOT NULL DEFAULT 'active',
            owner TEXT NOT NULL DEFAULT 'seven',
            created_at REAL NOT NULL,
            updated_at REAL,
            priority INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]'
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_steps (
            step_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'todo',
            owner TEXT NOT NULL DEFAULT 'seven',
            order_idx INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL,
            residual_risk TEXT,
            owner_route TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_blackboard_notes (
            note_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT 'seven',
            kind TEXT NOT NULL DEFAULT 'note',
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at REAL NOT NULL,
            updated_at REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_name TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            tags TEXT DEFAULT 'all'
        )"""
    )


def sync(db_path: Path = DB_PATH) -> dict[str, int]:
    now = time.time()
    stats = {"projects": 0, "steps": 0, "notes": 0, "docs": 0}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        for project_id, info in PROJECTS.items():
            existing = conn.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone()
            conn.execute(
                """INSERT INTO projects
                   (project_id, name, description, methodology, status, owner, created_at, updated_at, priority, tags)
                   VALUES (?, ?, 'System improvement tracking', 'mixed', 'active', 'seven', ?, ?, 8, ?)
                   ON CONFLICT(project_id) DO UPDATE SET
                     updated_at=excluded.updated_at,
                     priority=MAX(priority, excluded.priority),
                     tags=excluded.tags""",
                (project_id, info["name"], now, now, json.dumps(info["tags"])),
            )
            if not existing:
                stats["projects"] += 1

        for idx, (step_id, project_id, title, description, status) in enumerate(STEPS, start=1):
            existing = conn.execute("SELECT 1 FROM project_steps WHERE step_id=?", (step_id,)).fetchone()
            conn.execute(
                """INSERT INTO project_steps
                   (step_id, project_id, title, description, status, owner, order_idx, created_at, updated_at, owner_route)
                   VALUES (?, ?, ?, ?, ?, 'seven', ?, ?, ?, 'studio_git')
                   ON CONFLICT(step_id) DO UPDATE SET
                     title=excluded.title,
                     description=excluded.description,
                     status=excluded.status,
                     updated_at=excluded.updated_at,
                     owner_route=excluded.owner_route""",
                (step_id, project_id, title, description, status, idx, now, now),
            )
            if not existing:
                stats["steps"] += 1

        for idx, (project_id, kind, content) in enumerate(NOTES, start=1):
            existing = conn.execute(
                "SELECT 1 FROM project_blackboard_notes WHERE project_id=? AND content=? AND status!='archived'",
                (project_id, content),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """INSERT INTO project_blackboard_notes
                   (note_id, project_id, author, kind, content, status, created_at, updated_at)
                   VALUES (?, ?, 'codex', ?, ?, 'active', ?, ?)""",
                (f"B-STUDIO-GIT-APPCENTER-{idx:02d}", project_id, kind, content, now, now),
            )
            stats["notes"] += 1

        existing = conn.execute("SELECT 1 FROM project_docs WHERE doc_name=?", (DOC_NAME,)).fetchone()
        conn.execute(
            """INSERT INTO project_docs (doc_name, content, tags, updated_at)
               VALUES (?, ?, 'continuous-improvement,studio-git,app-center,project:P-00221285D1,project:P-855E64250C', datetime('now'))
               ON CONFLICT(doc_name) DO UPDATE SET
                 content=excluded.content,
                 tags=excluded.tags,
                 updated_at=datetime('now')""",
            (DOC_NAME, DOC_CONTENT),
        )
        if not existing:
            stats["docs"] += 1
        conn.commit()
    finally:
        conn.close()
    return stats


def main() -> int:
    stats = sync()
    print(
        "Logged Studio Git/App Center improvement: "
        f"{stats['projects']} projects, {stats['steps']} steps, "
        f"{stats['notes']} notes, {stats['docs']} docs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
