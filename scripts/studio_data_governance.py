#!/usr/bin/env python3
"""Studio-centered data governance audit and migration helper.

This script makes Fridays Studio and Knowledge Center the control plane for
project status, documentation traceability, and follow-up work.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("SWARM_DB_PATH", ROOT / "swarm_memory.db"))
CONTROL_PROJECT_NAME = "2026-04-29 Consolidated Improvement Project"
CONTROL_PROJECT_ID = "P-00221285D1"
CONTROL_PROPOSAL_ID = "DATA-GOV-20260429"
GENERATED_RETENTION_DAYS = 14
ARCHIVE_RETENTION_DAYS = 90

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    "target",
    "build",
    "dist",
    ".vs",
}

DOC_SUFFIXES = {".md", ".markdown", ".html", ".txt", ".rst"}
DATA_SUFFIXES = {".json", ".yaml", ".yml", ".db", ".sqlite", ".sqlite3"}
ACTIVE_AUXILIARY_DBS = {
    "swarm.db",
}
EMPTY_LEGACY_DBS = {
    "agents/swarm.db",
    "utils/swarm.db",
}

CANONICAL_DOC_PREFIXES = (
    "docs/",
    "README.md",
    "ops/",
    "windows/",
    "desktop/README.md",
)

ARCHIVE_PREFIXES = (
    "Archives/",
    "docs/archive/",
    ".history/",
    "sandpits_stage",
)

GENERATED_PREFIXES = (
    "swarm_docs/",
    "artifacts/",
    "tests/artifacts/",
)

SANDPIT_PREFIXES = ("sandpits/",)
RUNTIME_ASSET_PREFIXES = (
    "frontend/templates/",
)
AGENT_PROFILE_NAMES = {"personality.md", "BLUEPRINT.md", "diary.md"}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_real() -> float:
    return time.time()


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
            updated_at REAL
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
            updated_at REAL
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
        """CREATE TABLE IF NOT EXISTS project_test_cases (
            case_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            step_id TEXT,
            title TEXT NOT NULL,
            script_id TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            owner TEXT NOT NULL DEFAULT 'seven',
            created_at REAL NOT NULL,
            updated_at REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS proposal_projects (
            proposal_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (proposal_id, project_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_name TEXT NOT NULL,
            content TEXT DEFAULT '',
            tags TEXT DEFAULT 'all',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_doc_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER,
            doc_name TEXT,
            content TEXT,
            tags TEXT,
            version_number INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            source TEXT DEFAULT 'studio_data_governance'
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS work_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT UNIQUE NOT NULL,
            agent TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            proposal_file TEXT DEFAULT '',
            ticket_number TEXT DEFAULT '',
            queue_id INTEGER DEFAULT 0,
            source_node TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    ensure_column(conn, "work_proposals", "source_node", "TEXT DEFAULT ''")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            schedule TEXT,
            action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '',
            last_run TEXT,
            next_run TEXT,
            enabled INTEGER DEFAULT 1,
            created_by TEXT DEFAULT 'ghost',
            created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_2fa (
            username TEXT PRIMARY KEY,
            secret TEXT NOT NULL,
            verified_at REAL,
            created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS settings_sysmod (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS enrollment_invites (
            token TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            email TEXT,
            created_at REAL NOT NULL,
            consumed_at REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gmail_labels_cache (
            account TEXT NOT NULL,
            label_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT,
            message_count INTEGER,
            unread_count INTEGER,
            synced_at REAL NOT NULL,
            PRIMARY KEY (account, label_id)
        )"""
    )


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def migrate_auxiliary_dbs(conn: sqlite3.Connection) -> dict[str, int]:
    """Copy still-live auxiliary DB state into swarm_memory.db.

    This is intentionally one-way and idempotent. Runtime code now defaults to
    the central DB, but the old auxiliary files are left in place until the next
    cleanup review confirms no service still depends on them.
    """
    migrated: Counter[str] = Counter()
    swarm_aux = ROOT / "swarm.db"
    if swarm_aux.exists() and swarm_aux.stat().st_size > 0:
        aux = sqlite3.connect(swarm_aux)
        aux.row_factory = sqlite3.Row
        try:
            if _table_exists(aux, "user_2fa"):
                rows = aux.execute(
                    "SELECT username, secret, verified_at, created_at FROM user_2fa"
                ).fetchall()
                conn.executemany(
                    """INSERT OR IGNORE INTO user_2fa
                       (username, secret, verified_at, created_at)
                       VALUES (?, ?, ?, ?)""",
                    [(r["username"], r["secret"], r["verified_at"], r["created_at"]) for r in rows],
                )
                migrated["user_2fa"] += len(rows)
            if _table_exists(aux, "settings_sysmod"):
                rows = aux.execute(
                    "SELECT key, value, updated_at FROM settings_sysmod"
                ).fetchall()
                conn.executemany(
                    """INSERT OR REPLACE INTO settings_sysmod
                       (key, value, updated_at) VALUES (?, ?, ?)""",
                    [(r["key"], r["value"], r["updated_at"]) for r in rows],
                )
                migrated["settings_sysmod"] += len(rows)
            if _table_exists(aux, "enrollment_invites"):
                rows = aux.execute(
                    "SELECT token, role, email, created_at, consumed_at FROM enrollment_invites"
                ).fetchall()
                conn.executemany(
                    """INSERT OR IGNORE INTO enrollment_invites
                       (token, role, email, created_at, consumed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    [(r["token"], r["role"], r["email"], r["created_at"], r["consumed_at"]) for r in rows],
                )
                migrated["enrollment_invites"] += len(rows)
            if _table_exists(aux, "gmail_labels_cache"):
                rows = aux.execute(
                    """SELECT account, label_id, name, type, message_count,
                              unread_count, synced_at
                       FROM gmail_labels_cache"""
                ).fetchall()
                conn.executemany(
                    """INSERT OR REPLACE INTO gmail_labels_cache
                       (account, label_id, name, type, message_count, unread_count, synced_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            r["account"], r["label_id"], r["name"], r["type"],
                            r["message_count"], r["unread_count"], r["synced_at"],
                        )
                        for r in rows
                    ],
                )
                migrated["gmail_labels_cache"] += len(rows)
        finally:
            aux.close()

    studio_aux = ROOT / "studio_proposals.db"
    if studio_aux.exists() and studio_aux.stat().st_size > 0:
        aux = sqlite3.connect(studio_aux)
        aux.row_factory = sqlite3.Row
        try:
            if _table_exists(aux, "work_proposals"):
                rows = aux.execute(
                    """SELECT id, title, description, status, created_at,
                              git_branch, studio_link
                       FROM work_proposals"""
                ).fetchall()
                for row in rows:
                    proposal_id = f"STUDIO-PROPOSALS-{int(row['id']):04d}"
                    conn.execute(
                        """INSERT OR IGNORE INTO work_proposals
                           (proposal_id, agent, title, description, status, git_branch, source_node, created_at, updated_at)
                           VALUES (?, 'studio', ?, ?, ?, ?, 'studio_proposals.db', ?, datetime('now'))""",
                        (
                            proposal_id,
                            str(row["title"] or "")[:256],
                            row["description"] or "",
                            row["status"] or "pending",
                            row["git_branch"] or row["studio_link"] or "",
                            row["created_at"] or now_text(),
                        ),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO proposal_projects (proposal_id, project_id, created_at) VALUES (?, ?, ?)",
                        (proposal_id, CONTROL_PROJECT_ID, now_real()),
                    )
                migrated["studio_proposals_work_proposals"] += len(rows)
        finally:
            aux.close()
    return dict(migrated)


def stable_id(prefix: str, text: str) -> str:
    import hashlib

    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10].upper()}"


def ensure_control_project(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT project_id FROM projects WHERE project_id=?",
        (CONTROL_PROJECT_ID,),
    ).fetchone()
    if row:
        project_id = row["project_id"]
        conn.execute(
            "UPDATE projects SET name=?, status='active', updated_at=? WHERE project_id=?",
            (CONTROL_PROJECT_NAME, now_real(), project_id),
        )
        return project_id

    row = conn.execute(
        "SELECT project_id FROM projects WHERE name=? ORDER BY created_at LIMIT 1",
        (CONTROL_PROJECT_NAME,),
    ).fetchone()
    if row:
        project_id = row["project_id"]
        conn.execute(
            "UPDATE projects SET status='active', updated_at=? WHERE project_id=?",
            (now_real(), project_id),
        )
        return project_id

    project_id = CONTROL_PROJECT_ID
    ts = now_real()
    conn.execute(
        """INSERT INTO projects
           (project_id, name, description, methodology, status, owner, created_at, updated_at)
           VALUES (?, ?, ?, 'prince2', 'active', 'seven', ?, ?)""",
        (
            project_id,
            CONTROL_PROJECT_NAME,
            "Control project for consolidating documentation, runtime data, Knowledge Center records, and ALM traceability into Fridays Studio.",
            ts,
            ts,
        ),
    )
    return project_id


def ensure_proposal(conn: sqlite3.Connection, project_id: str) -> None:
    conn.execute(
        """INSERT INTO work_proposals
           (proposal_id, agent, title, description, status, source_node, updated_at)
           VALUES (?, 'ghost_coder', ?, ?, 'in_progress', 'studio_data_governance', datetime('now'))
           ON CONFLICT(proposal_id) DO UPDATE SET
             title=excluded.title,
             description=excluded.description,
             status='in_progress',
             updated_at=datetime('now')""",
        (
            CONTROL_PROPOSAL_ID,
            "Centralise project documentation and data governance in Fridays Studio",
            "ALM control record for the data/file architecture cleanup. All findings, decisions, next steps, and trace reports are stored in Studio Projects and Knowledge Center.",
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO proposal_projects (proposal_id, project_id, created_at) VALUES (?, ?, ?)",
        (CONTROL_PROPOSAL_ID, project_id, now_real()),
    )


def upsert_step(
    conn: sqlite3.Connection,
    project_id: str,
    title: str,
    description: str,
    status: str,
    order_idx: int,
) -> str:
    row = conn.execute(
        "SELECT step_id FROM project_steps WHERE project_id=? AND title=?",
        (project_id, title),
    ).fetchone()
    ts = now_real()
    if row:
        step_id = row["step_id"]
        conn.execute(
            """UPDATE project_steps
               SET description=?, status=?, owner='seven', order_idx=?, updated_at=?
               WHERE step_id=?""",
            (description, status, order_idx, ts, step_id),
        )
        return step_id

    step_id = stable_id("S", f"{project_id}:{title}")
    conn.execute(
        """INSERT INTO project_steps
           (step_id, project_id, title, description, status, owner, order_idx, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'seven', ?, ?, ?)""",
        (step_id, project_id, title, description, status, order_idx, ts, ts),
    )
    return step_id


def add_blackboard_once(
    conn: sqlite3.Connection,
    project_id: str,
    kind: str,
    content: str,
) -> None:
    row = conn.execute(
        "SELECT note_id FROM project_blackboard_notes WHERE project_id=? AND content=?",
        (project_id, content),
    ).fetchone()
    if row:
        return
    note_id = stable_id("N", f"{project_id}:{kind}:{content}")
    ts = now_real()
    conn.execute(
        """INSERT INTO project_blackboard_notes
           (note_id, project_id, author, kind, content, status, created_at, updated_at)
           VALUES (?, ?, 'seven', ?, ?, 'active', ?, ?)""",
        (note_id, project_id, kind, content, ts, ts),
    )


def classify_path(path: Path) -> str:
    rel = path.as_posix()
    if rel.startswith(RUNTIME_ASSET_PREFIXES):
        return "code_or_asset"
    if len(path.parts) >= 3 and path.parts[0] == "agents" and path.name in AGENT_PROFILE_NAMES:
        return "agent_profile_source"
    if rel == ".instructions.md":
        return "reference_doc"
    if rel == "requirements.txt":
        return "code_or_asset"
    if rel == "audit/audit.md":
        return "reference_doc"
    if rel.startswith("tests/") and path.suffix.lower() == ".txt":
        return "generated_output"
    if rel.startswith("skills/") and path.suffix.lower() == ".md":
        return "archive"
    if rel.startswith(ARCHIVE_PREFIXES):
        return "archive"
    if rel.startswith(GENERATED_PREFIXES):
        return "generated_output"
    if rel.startswith(SANDPIT_PREFIXES):
        return "sandpit_working_note"
    if rel.startswith(CANONICAL_DOC_PREFIXES):
        return "reference_doc"
    if path.suffix in {".db", ".sqlite", ".sqlite3"}:
        if rel == "swarm_memory.db":
            return "runtime_source_of_truth"
        if rel in EMPTY_LEGACY_DBS:
            return "empty_legacy_db"
        if rel in ACTIVE_AUXILIARY_DBS:
            return "active_auxiliary_db"
        return "duplicate_or_legacy_db"
    if path.suffix in DOC_SUFFIXES:
        return "loose_document"
    if path.suffix in DATA_SUFFIXES:
        return "structured_data"
    return "code_or_asset"


def iter_files() -> list[Path]:
    results: list[Path] = []
    for path in ROOT.rglob("*"):
        rel_parts = path.relative_to(ROOT).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        if "llama.cpp" in rel_parts or "models" in rel_parts:
            continue
        if path.is_file():
            results.append(path.relative_to(ROOT))
    return sorted(results, key=lambda p: p.as_posix())


def inventory() -> dict[str, Any]:
    files = iter_files()
    entries: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    by_top: dict[str, Counter[str]] = defaultdict(Counter)

    for rel in files:
        full = ROOT / rel
        classification = classify_path(rel)
        counts[classification] += 1
        suffix_counts[rel.suffix.lower() or "[none]"] += 1
        top = rel.parts[0] if rel.parts else "."
        by_top[top][classification] += 1
        if classification != "code_or_asset":
            stat = full.stat()
            entries.append(
                {
                    "path": rel.as_posix(),
                    "classification": classification,
                    "size": stat.st_size,
                    "suffix": rel.suffix.lower(),
                    "mtime": stat.st_mtime,
                    "mtime_text": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

    return {
        "generated_at": now_text(),
        "db_path": str(DB_PATH),
        "total_files_scanned": len(files),
        "classification_counts": dict(counts),
        "suffix_counts": dict(suffix_counts.most_common(30)),
        "top_level_counts": {
            key: dict(value) for key, value in sorted(by_top.items())
        },
        "tracked_non_code_files": entries,
    }


def project_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT p.project_id, p.name, p.status, p.methodology, p.owner,
                  datetime(p.updated_at, 'unixepoch') AS updated_at,
                  COUNT(s.step_id) AS steps,
                  SUM(CASE WHEN s.status IN ('todo','doing','blocked','partial') THEN 1 ELSE 0 END) AS open_steps,
                  SUM(CASE WHEN s.status='doing' THEN 1 ELSE 0 END) AS doing_steps
           FROM projects p
           LEFT JOIN project_steps s ON s.project_id=p.project_id
           GROUP BY p.project_id
           ORDER BY p.status='active' DESC, p.updated_at DESC"""
    ).fetchall()
    proposals = conn.execute(
        """SELECT proposal_id, agent, status, title, updated_at
           FROM work_proposals ORDER BY updated_at DESC"""
    ).fetchall()
    tasks = conn.execute(
        """SELECT name, schedule, action_type, action_data, enabled
           FROM scheduled_tasks ORDER BY id"""
    ).fetchall()
    return {
        "generated_at": now_text(),
        "projects": [dict(r) for r in rows],
        "work_proposals": [dict(r) for r in proposals],
        "scheduled_tasks": [dict(r) for r in tasks],
    }


def portfolio_focus_doc(status: dict[str, Any]) -> str:
    active = [
        f"{p.get('project_id')} {p.get('name')}"
        for p in status.get("projects", [])
        if p.get("status") == "active"
    ]
    payload = {
        "generated_at": now_text(),
        "source_of_truth": "Fridays Studio Projects + Knowledge Center in swarm_memory.db",
        "current_focus": active,
        "on_hold_policy": (
            "Projects stay on_hold until they have a clear Studio next step, "
            "Knowledge Center references, and ALM-linked proposal/task evidence."
        ),
        "portfolio": status.get("projects", []),
    }
    return render_markdown("Studio Portfolio Current Focus", payload)


def cleanup_candidates(inv: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    files = inv["tracked_non_code_files"]
    duplicate_dbs = [f for f in files if f["classification"] == "duplicate_or_legacy_db"]
    active_aux_dbs = [f for f in files if f["classification"] == "active_auxiliary_db"]
    empty_legacy_dbs = [f for f in files if f["classification"] == "empty_legacy_db"]
    archive_docs = [f for f in files if f["classification"] == "archive"]
    sandpit_notes = [f for f in files if f["classification"] == "sandpit_working_note"]
    loose_docs = [f for f in files if f["classification"] == "loose_document"]
    generated = [f for f in files if f["classification"] == "generated_output"]
    active_projects = [p for p in status["projects"] if p["status"] == "active"]

    archive_project_candidates = [
        p for p in active_projects
        if (p["open_steps"] or 0) == 0
        or p["name"].lower().startswith(("self-test", "smoke"))
        or p["name"].lower() in {"x"}
        or "probe" in p["name"].lower()
    ]

    split_project_candidates = [
        p for p in active_projects if (p["open_steps"] or 0) > 50
    ]

    return {
        "generated_at": now_text(),
        "archive_project_candidates": archive_project_candidates,
        "split_project_candidates": split_project_candidates,
        "duplicate_or_legacy_dbs": duplicate_dbs,
        "active_auxiliary_dbs": active_aux_dbs,
        "empty_legacy_dbs": empty_legacy_dbs,
        "loose_documents": loose_docs,
        "archive_documents": archive_docs[:250],
        "sandpit_working_notes": sandpit_notes[:250],
        "generated_outputs": generated[:250],
        "retention_manifest": retention_manifest(inv),
        "policy": {
            "source_of_truth": "Fridays Studio Projects + Knowledge Center in swarm_memory.db",
            "repo_docs_role": "Stable reference/runbooks only, each mirrored into Knowledge Center with project tags.",
            "sandpits_role": "Short-lived working notes only; project decisions must be summarized into Studio blackboard.",
            "archives_role": "Cold historical storage; not used for active planning.",
            "generated_role": "Regenerable indexes/reports; not used as planning truth.",
        },
    }


def _age_days(item: dict[str, Any]) -> float:
    try:
        return max(0.0, (time.time() - float(item.get("mtime") or time.time())) / 86400.0)
    except Exception:
        return 0.0


def retention_manifest(inv: dict[str, Any]) -> dict[str, Any]:
    """Build the reviewable cleanup manifest; never deletes by itself.

    The repository has thousands of historical files. This manifest separates
    things that are safe to review for removal from things that should remain
    as reference/archive material. Destructive cleanup should consume this KC
    record and require operator confirmation.
    """
    review_items: list[dict[str, Any]] = []
    keep_items: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for item in inv.get("tracked_non_code_files") or []:
        classification = item.get("classification") or "unknown"
        rel = item.get("path") or ""
        age = _age_days(item)
        base = {
            "path": rel,
            "classification": classification,
            "size": item.get("size", 0),
            "mtime_text": item.get("mtime_text", ""),
            "age_days": round(age, 1),
        }
        if classification == "duplicate_or_legacy_db":
            counts["operator_review_required"] += 1
            review_items.append({
                **base,
                "recommended_action": "review_then_archive_or_delete",
                "reason": "Only swarm_memory.db is the runtime source of truth; legacy DBs can mislead agents.",
                "guard": "Confirm no code path or backup policy still references this DB before deletion.",
            })
        elif classification == "active_auxiliary_db":
            counts["migration_required"] += 1
            review_items.append({
                **base,
                "recommended_action": "migrate_to_swarm_memory_then_retire",
                "reason": "Auxiliary DB state has a central migration path; keep the file until restart verification confirms central DB reads are stable.",
                "guard": "Remove after endpoint smoke tests pass without SWARM_DB or SWARM_2FA_DB overrides.",
            })
        elif classification == "empty_legacy_db":
            counts["empty_legacy_delete_candidate"] += 1
            review_items.append({
                **base,
                "recommended_action": "delete_empty_placeholder",
                "reason": "Zero-byte legacy DB placeholder with no active code reference.",
                "guard": "Safe to remove after confirming it remains zero bytes and untracked.",
            })
        elif classification == "loose_document":
            counts["promote_or_archive_required"] += 1
            review_items.append({
                **base,
                "recommended_action": "promote_to_kc_then_archive_repo_copy",
                "reason": "Active docs must be attached to Studio/KC or reclassified as reference/archive.",
                "guard": "Create or update a Knowledge Center record before moving/deleting the repo copy.",
            })
        elif classification == "generated_output" and age >= GENERATED_RETENTION_DAYS:
            counts["generated_delete_candidate"] += 1
            review_items.append({
                **base,
                "recommended_action": "delete_if_regenerable",
                "reason": f"Generated output older than {GENERATED_RETENTION_DAYS} days.",
                "guard": "Delete only if regenerated by scripts/tests and not referenced by a project step.",
            })
        elif classification == "archive" and age >= ARCHIVE_RETENTION_DAYS:
            counts["cold_archive_keep"] += 1
            keep_items.append({
                **base,
                "recommended_action": "keep_cold_archive",
                "reason": f"Archive file older than {ARCHIVE_RETENTION_DAYS} days; not active planning truth.",
            })

    return {
        "generated_at": now_text(),
        "destructive_actions_taken": False,
        "retention_days": {
            "generated_output": GENERATED_RETENTION_DAYS,
            "archive": ARCHIVE_RETENTION_DAYS,
        },
        "counts": dict(counts),
        "review_items": review_items[:500],
        "cold_archive_examples": keep_items[:100],
    }


def render_markdown(title: str, payload: dict[str, Any]) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```\n"


def upsert_kb_doc(conn: sqlite3.Connection, name: str, content: str, tags: str) -> int:
    row = conn.execute(
        "SELECT id, content, tags FROM project_docs WHERE doc_name=? ORDER BY id LIMIT 1",
        (name,),
    ).fetchone()
    if row:
        doc_id = int(row["id"])
        if (row["content"] or "") == content and (row["tags"] or "") == tags:
            return doc_id
        conn.execute(
            "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
            (content, tags, doc_id),
        )
        action = "update"
    else:
        cur = conn.execute(
            "INSERT INTO project_docs (doc_name, content, tags) VALUES (?, ?, ?)",
            (name, content, tags),
        )
        doc_id = int(cur.lastrowid)
        action = "create"

    version_row = conn.execute(
        "SELECT COALESCE(MAX(version_number), 0) AS v FROM project_doc_versions WHERE doc_id=?",
        (doc_id,),
    ).fetchone()
    version = int((version_row["v"] if version_row else 0) or 0) + 1
    conn.execute(
        """INSERT INTO project_doc_versions
           (doc_id, doc_name, content, tags, version_number, action, source)
           VALUES (?, ?, ?, ?, ?, ?, 'studio_data_governance')""",
        (doc_id, name, content, tags, version, action),
    )
    return doc_id


def mirror_active_repo_docs(
    conn: sqlite3.Connection,
    inv: dict[str, Any],
    project_id: str,
    proposal_id: str,
) -> dict[str, int]:
    mirrored: dict[str, int] = {}
    for item in inv.get("tracked_non_code_files") or []:
        classification = item.get("classification")
        if classification not in {"reference_doc", "agent_profile_source"}:
            continue
        rel = item.get("path") or ""
        path = ROOT / rel
        if not path.exists() or path.stat().st_size > 250_000:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        doc_name = f"Repo Mirror - {rel}"
        tags = (
            f"project:{project_id},alm:{proposal_id},repo-mirror,"
            f"classification:{classification},path:{rel}"
        )
        mirrored[rel] = upsert_kb_doc(conn, doc_name, content, tags)
    return mirrored


def archive_obvious_stale_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT p.project_id, p.name, p.status,
                  SUM(CASE WHEN s.status IN ('todo','doing','blocked','partial') THEN 1 ELSE 0 END) AS open_steps
           FROM projects p
           LEFT JOIN project_steps s ON s.project_id=p.project_id
           WHERE p.status='active'
           GROUP BY p.project_id"""
    ).fetchall()
    archived: list[dict[str, Any]] = []
    for row in rows:
        name = row["name"] or ""
        open_steps = int(row["open_steps"] or 0)
        lower = name.lower()
        should_archive = (
            open_steps == 0
            or lower.startswith(("self-test", "smoke"))
            or lower == "x"
            or "probe" in lower
        )
        if not should_archive:
            continue
        conn.execute(
            "UPDATE projects SET status='archived', updated_at=? WHERE project_id=?",
            (now_real(), row["project_id"]),
        )
        archived.append({"project_id": row["project_id"], "name": name, "open_steps": open_steps})
    return archived


def ensure_control_steps(conn: sqlite3.Connection, project_id: str) -> dict[str, str]:
    steps = [
        (
            "ALM control record and Studio project created",
            "Create the governing proposal/project record so cleanup is traceable through Fridays Studio.",
            "done",
        ),
        (
            "Repository file inventory captured",
            "Classify docs, data files, generated outputs, archives, sandpit notes, and DB files.",
            "done",
        ),
        (
            "Knowledge Center governance docs published",
            "Store inventory, status report, cleanup policy, and migration candidates in project_docs with versions.",
            "done",
        ),
        (
            "Archive obvious stale Studio projects",
            "Archive active smoke/probe/completed projects so current focus becomes readable.",
            "done",
        ),
        (
            "Consolidate active mega-project backlog",
            "Split or group Integration Improvement Audit steps into smaller workstreams with current-focus lanes.",
            "doing",
        ),
        (
            "Attach loose documents to project records",
            "Summarize active loose docs into Studio blackboard/project docs, then mark repo copies as reference/archive/generated.",
            "done",
        ),
        (
            "Publish deletion manifest and retention gate",
            "Create a Knowledge Center manifest for legacy DBs, old generated outputs, and cleanup review gates before any destructive file operation.",
            "done",
        ),
        (
            "Add automated governance sweep",
            "Schedule a weekly Tasker sweep that reports new loose docs, duplicate DBs, stale sandpit notes, and unlinked projects.",
            "done",
        ),
        (
            "Review legacy DB and generated-output cleanup candidates",
            "Use the Knowledge Center deletion manifest to confirm which auxiliary DBs and generated artifacts can be migrated, archived, or deleted.",
            "doing",
        ),
        (
            "Migrate active auxiliary DB tables into swarm_memory.db",
            "Move swarm.db state such as 2FA, enrollment, sysmod, and Gmail label cache plus studio_proposals.db work proposal state into the central DB before retiring those files.",
            "done",
        ),
        (
            "Retire final swarm.db after restart verification",
            "After the app restarts on the central DB paths, confirm 2FA/sysmod/enrollment/Gmail-label endpoints read swarm_memory.db and then remove the final swarm.db copy.",
            "doing",
        ),
        (
            "Enforce project-linked work intake",
            "Add checks/warnings so new docs, proposals, and Tasker work declare a Studio project or Knowledge Center tag.",
            "done",
        ),
    ]
    step_ids: dict[str, str] = {}
    for idx, (title, description, status) in enumerate(steps):
        step_ids[title] = upsert_step(conn, project_id, title, description, status, idx)
    return step_ids


def apply_governance() -> dict[str, Any]:
    inv = inventory()
    with connect() as conn:
        ensure_schema(conn)
        project_id = ensure_control_project(conn)
        ensure_proposal(conn, project_id)
        migrated_auxiliary = migrate_auxiliary_dbs(conn)
        step_ids = ensure_control_steps(conn, project_id)
        archived_projects = archive_obvious_stale_projects(conn)
        status = project_status(conn)
        candidates = cleanup_candidates(inv, status)

        tags = f"project:{project_id},alm:{CONTROL_PROPOSAL_ID},data-governance,studio-source-of-truth"
        docs = {
            "Studio Data Governance - Repository Inventory": render_markdown(
                "Studio Data Governance - Repository Inventory", inv
            ),
            "Studio Data Governance - Project Status Report": render_markdown(
                "Studio Data Governance - Project Status Report", status
            ),
            "Studio Data Governance - Cleanup Candidates and Policy": render_markdown(
                "Studio Data Governance - Cleanup Candidates and Policy", candidates
            ),
            "Studio Data Governance - Deletion Manifest and Retention Gate": render_markdown(
                "Studio Data Governance - Deletion Manifest and Retention Gate",
                candidates.get("retention_manifest") or {},
            ),
            "Studio Data Governance - Operating Model": (
                "# Studio Data Governance - Operating Model\n\n"
                "Fridays Studio Projects and Knowledge Center are the source of truth. "
                "Repository files are implementation, stable reference, generated output, "
                "or archive. Active planning belongs in project steps, blackboard notes, "
                "test cases, scheduled tasks, and ALM proposals linked to a project.\n\n"
                "Required intake rule: every new work item must have a Studio project id "
                "or must create one before code, docs, research, or Tasker automation begins.\n\n"
                "Required closeout rule: every completed change must update the linked "
                "project step, add test evidence, and record a compact Knowledge Center "
                "or blackboard note.\n"
            ),
            "Studio Portfolio Current Focus": portfolio_focus_doc(status),
        }
        doc_ids = {
            name: upsert_kb_doc(conn, name, content, tags)
            for name, content in docs.items()
        }
        mirrored_docs = mirror_active_repo_docs(conn, inv, project_id, CONTROL_PROPOSAL_ID)

        add_blackboard_once(
            conn,
            project_id,
            "decision",
            "Decision: Fridays Studio Projects plus Knowledge Center in swarm_memory.db are now the operating source of truth for active project state, documentation traceability, and next actions.",
        )
        add_blackboard_once(
            conn,
            project_id,
            "risk",
            "Risk: duplicate DB files and historical Markdown can mislead agents unless governance sweeps keep Studio/KC links current.",
        )
        add_blackboard_once(
            conn,
            project_id,
            "handoff",
            "Handoff: continue by splitting P-BD5B54E749 into smaller active workstreams and linking high-value loose docs into Knowledge Center records tagged to their Studio projects.",
        )
        add_blackboard_once(
            conn,
            project_id,
            "decision",
            "Decision: destructive document cleanup must use the Knowledge Center deletion manifest first; generated files and legacy DBs are reviewed before removal, not deleted blindly.",
        )
        add_blackboard_once(
            conn,
            project_id,
            "decision",
            "Decision: new ALM proposals are now linked to a Studio project at intake, defaulting to the consolidated control project when no explicit project id is supplied.",
        )
        if migrated_auxiliary:
            add_blackboard_once(
                conn,
                project_id,
                "handoff",
                "Handoff: auxiliary DB state copied into swarm_memory.db: "
                + json.dumps(migrated_auxiliary, sort_keys=True)
                + ". Keep swarm.db/studio_proposals.db until runtime verification confirms central DB reads are stable.",
            )

        conn.commit()

    return {
        "project_id": project_id,
        "proposal_id": CONTROL_PROPOSAL_ID,
        "step_ids": step_ids,
        "knowledge_doc_ids": doc_ids,
        "mirrored_repo_docs": len(mirrored_docs),
        "archived_projects": archived_projects,
        "migrated_auxiliary": migrated_auxiliary,
        "inventory_counts": inv["classification_counts"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write Studio/KC governance state")
    parser.add_argument("--manifest", action="store_true", help="print cleanup retention manifest")
    parser.add_argument("--check", action="store_true", help="exit non-zero when loose docs or legacy DBs need review")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args()

    if args.apply:
        result = apply_governance()
    else:
        inv = inventory()
        if args.manifest:
            result = retention_manifest(inv)
        else:
            result = inv
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    if args.check:
        counts = result.get("inventory_counts") if args.apply else result.get("classification_counts")
        counts = counts or {}
        if counts.get("loose_document", 0) or counts.get("duplicate_or_legacy_db", 0):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
