#!/usr/bin/env python3
"""Seed the Grok-Pot-Money-Maker sandpit into Studio.

The Grok branch created useful project files, but Studio only had an empty
project shell. This sync keeps the disk plan and the Studio DB aligned without
pulling in Grok's incomplete loader changes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from pathlib import Path


PROJECT_ID = "P-855E64250C"
PROJECT_NAME = "Grok-Pot-Money-Maker"
ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT / "sandpits" / "studio" / PROJECT_NAME
RELATED_DIR = ROOT / "sandpits" / "studio" / "grok_pot"


TASK_RE = re.compile(r"^\s*\d+\.\s+\[(?P<mark>[ xX])\]\s+(?P<title>.+?)\s*$")


def default_db_path() -> Path:
    return Path(
        os.environ.get("SWARM_DB_PATH")
        or os.environ.get("SWARM_DB")
        or ROOT / "swarm_memory.db"
    )


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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_tasks(plan_text: str) -> list[tuple[str, str]]:
    tasks: list[tuple[str, str]] = []
    for line in plan_text.splitlines():
        match = TASK_RE.match(line)
        if not match:
            continue
        status = "done" if match.group("mark").lower() == "x" else "todo"
        tasks.append((status, match.group("title").strip()))
    return tasks


def parse_blackboard(plan_text: str) -> list[str]:
    notes: list[str] = []
    in_section = False
    for line in plan_text.splitlines():
        if line.startswith("## "):
            in_section = line.strip().lower() == "## blackboard notes"
            continue
        if in_section and line.strip().startswith("- "):
            notes.append(line.strip()[2:].strip())
    return notes


def project_docs() -> list[Path]:
    paths = [
        PROJECT_DIR / "PROJECT_PLAN.md",
        PROJECT_DIR / "newsletter" / "NEWSLETTER_BLUEPRINT.md",
        PROJECT_DIR / "building_blocks" / "MONEY_BOT_BUILDING_BLOCK.py",
        RELATED_DIR / "README.md",
        RELATED_DIR / "REVIEW_2026-05-09.md",
        RELATED_DIR / "PROJECT_PLAN.md",
        RELATED_DIR / "MONEY_BOTS.md",
        RELATED_DIR / "NEWSLETTER_TEMPLATE.md",
        RELATED_DIR / "TRADING_GAME_KC.md",
    ]
    return [p for p in paths if p.exists()]


def relative_doc_name(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sync(db_path: Path | None = None) -> dict[str, int]:
    db_path = db_path or default_db_path()
    plan_path = PROJECT_DIR / "PROJECT_PLAN.md"
    plan_text = read_text(plan_path)
    tasks = parse_tasks(plan_text)
    notes = parse_blackboard(plan_text)
    now = time.time()
    stats = {"projects": 0, "steps": 0, "notes": 0, "docs": 0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        tags = json.dumps(["grok-pot", "money-maker", "studio-git", "intake"])
        description = (
            "Studio intake for Grok Pot Money Maker. The revenue ideas are "
            "parked until Studio Git visibility, DEV/UAT branch selection, "
            "and Blackboard visibility are reliable."
        )
        existing = conn.execute(
            "SELECT 1 FROM projects WHERE project_id=?", (PROJECT_ID,)
        ).fetchone()
        conn.execute(
            """INSERT INTO projects
               (project_id, name, description, methodology, status, owner,
                created_at, updated_at, priority, tags)
               VALUES (?, ?, ?, 'mixed', 'active', 'seven', ?, ?, 8, ?)
               ON CONFLICT(project_id) DO UPDATE SET
                 name=excluded.name,
                 description=excluded.description,
                 methodology=excluded.methodology,
                 status=excluded.status,
                 owner=excluded.owner,
                 updated_at=excluded.updated_at,
                 priority=excluded.priority,
                 tags=excluded.tags""",
            (PROJECT_ID, PROJECT_NAME, description, now, now, tags),
        )
        stats["projects"] = 0 if existing else 1

        for idx, (status, title) in enumerate(tasks, start=1):
            step_id = f"S-P855E64250C-{idx:02d}"
            step_desc = (
                f"Imported from {relative_doc_name(plan_path)}. "
                "Keep this aligned with the sandpit project plan."
            )
            existing = conn.execute(
                "SELECT 1 FROM project_steps WHERE step_id=?", (step_id,)
            ).fetchone()
            conn.execute(
                """INSERT INTO project_steps
                   (step_id, project_id, title, description, status, owner,
                    order_idx, created_at, updated_at, owner_route)
                   VALUES (?, ?, ?, ?, ?, 'seven', ?, ?, ?, 'studio_git')
                   ON CONFLICT(step_id) DO UPDATE SET
                     project_id=excluded.project_id,
                     title=excluded.title,
                     description=excluded.description,
                     status=excluded.status,
                     owner=excluded.owner,
                     order_idx=excluded.order_idx,
                     updated_at=excluded.updated_at,
                     owner_route=excluded.owner_route""",
                (step_id, PROJECT_ID, title, step_desc, status, idx, now, now),
            )
            if not existing:
                stats["steps"] += 1

        for idx, content in enumerate(notes, start=1):
            existing = conn.execute(
                """SELECT 1 FROM project_blackboard_notes
                   WHERE project_id=? AND content=? AND status!='archived'""",
                (PROJECT_ID, content),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """INSERT INTO project_blackboard_notes
                   (note_id, project_id, author, kind, content, status,
                    created_at, updated_at)
                   VALUES (?, ?, 'codex', 'handoff', ?, 'active', ?, ?)""",
                (f"B-P855E64250C-{idx:02d}", PROJECT_ID, content, now, now),
            )
            stats["notes"] += 1

        for path in project_docs():
            doc_name = relative_doc_name(path)
            existing = conn.execute(
                "SELECT 1 FROM project_docs WHERE doc_name=?", (doc_name,)
            ).fetchone()
            doc_tags = "grok-pot,money-maker,project:P-855E64250C"
            conn.execute(
                """INSERT INTO project_docs (doc_name, content, tags, updated_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(doc_name) DO UPDATE SET
                     content=excluded.content,
                     tags=excluded.tags,
                     updated_at=datetime('now')""",
                (doc_name, read_text(path), doc_tags),
            )
            if not existing:
                stats["docs"] += 1

        conn.commit()
    finally:
        conn.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=None, help="SQLite DB path")
    args = parser.parse_args()
    stats = sync(args.db)
    print(
        "Synced Grok-Pot-Money-Maker to Studio: "
        f"{stats['projects']} project, {stats['steps']} steps, "
        f"{stats['notes']} notes, {stats['docs']} docs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
