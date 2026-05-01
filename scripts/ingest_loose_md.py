#!/usr/bin/env python3
"""PACKET-01: Ingest loose .md files into Studio project_docs and archive
the doc-class originals to Archives/ingested_md_20260501/ with a manifest.

Two pools:
  INDEX_ONLY  - runtime files we register in project_docs but DO NOT move
                (agent personalities, diaries, vendored model READMEs).
  INGEST_AND_ARCHIVE - real docs we register + relocate under Archives/.

Idempotent: doc_name is UNIQUE; existing rows are UPDATED with a new
project_doc_versions row written first.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "swarm_memory.db"
ARCHIVE_DIR = ROOT / "Archives" / "ingested_md_20260501"
PROJECT = "P-00221285D1"
TAG_BASE = f"{PROJECT},sweep-202605-01,ingested"

INDEX_ONLY_GLOBS = [
    "agents/*/personality.md",
    "agents/seven/BLUEPRINT.md",
    "agents/seven/diary.md",
    "agents/seven/models/*/README.md",
    "sandpits_stage1/README.md",
    "sandpits_stage2/README.md",
    "sandpits_stage3/README.md",
]

INGEST_AND_ARCHIVE_GLOBS = [
    "README.md",
    ".instructions.md",
    "docs/*.md",
    "docs/api/*.md",
    "docs/archive/*.md",
    "docs/audits/*.md",
    "docs/reference/*.md",
    "docs/registry/*.md",
    "docs/runbooks/*.md",
    "docs/testing/*.md",
    "ops/*.md",
    "ops/kc_seeds/*.md",
    "swarm_docs/*.md",
    "windows/README.md",
    "desktop/README.md",
]


def _gather(patterns: list[str]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in patterns:
        for p in ROOT.glob(pat):
            if p.is_file() and p.suffix == ".md" and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _category_for(rel: str) -> str:
    if rel.startswith("agents/"):
        return "runtime-agent"
    if rel.startswith("docs/archive/"):
        return "doc-archive"
    if rel.startswith("docs/runbooks/"):
        return "runbook"
    if rel.startswith("docs/testing/"):
        return "testing-doc"
    if rel.startswith("docs/audits/"):
        return "audit-doc"
    if rel.startswith("docs/registry/"):
        return "registry-doc"
    if rel.startswith("docs/reference/"):
        return "reference-doc"
    if rel.startswith("docs/api/"):
        return "api-doc"
    if rel.startswith("docs/"):
        return "core-doc"
    if rel.startswith("ops/"):
        return "ops-doc"
    if rel.startswith("swarm_docs/"):
        return "system-index"
    if rel.startswith("windows/") or rel.startswith("desktop/"):
        return "subsystem-readme"
    if rel.startswith("sandpits_stage"):
        return "sandpit-readme"
    if rel == "README.md":
        return "root-readme"
    if rel == ".instructions.md":
        return "instructions"
    return "doc"


def _upsert(conn: sqlite3.Connection, doc_name: str, content: str, tags: str) -> str:
    cur = conn.execute("SELECT id, content FROM project_docs WHERE doc_name=?", (doc_name,))
    row = cur.fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO project_docs (doc_name, content, tags) VALUES (?, ?, ?)",
            (doc_name, content, tags),
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO project_doc_versions (doc_id, doc_name, content, tags, version_number, action, source) "
            "VALUES (?, ?, ?, ?, 1, 'create', 'sweep-202605-01')",
            (new_id, doc_name, content, tags),
        )
        return "create"
    doc_id, old_content = row
    if old_content == content:
        # still refresh tags so linkage is set
        conn.execute("UPDATE project_docs SET tags=? WHERE id=?", (tags, doc_id))
        return "skip-same"
    nv = conn.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 FROM project_doc_versions WHERE doc_id=?",
        (doc_id,),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO project_doc_versions (doc_id, doc_name, content, tags, version_number, action, source) "
        "VALUES (?, ?, ?, ?, ?, 'update', 'sweep-202605-01')",
        (doc_id, doc_name, content, tags, nv),
    )
    conn.execute(
        "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
        (content, tags, doc_id),
    )
    return "update"


def main() -> int:
    if not DB.exists():
        print(f"db missing: {DB}")
        return 1
    index_only = _gather(INDEX_ONLY_GLOBS)
    ingest_archive = _gather(INGEST_AND_ARCHIVE_GLOBS)
    print(f"index-only: {len(index_only)}    ingest+archive: {len(ingest_archive)}")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    counts = {"create": 0, "update": 0, "skip-same": 0, "archived": 0}

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            for path in index_only + ingest_archive:
                rel = path.relative_to(ROOT).as_posix()
                content = path.read_text(encoding="utf-8", errors="replace")
                cat = _category_for(rel)
                tags = f"{TAG_BASE},{cat}"
                action = _upsert(conn, rel, content, tags)
                counts[action] = counts.get(action, 0) + 1
                manifest.append({
                    "source": rel,
                    "doc_name": rel,
                    "category": cat,
                    "action": action,
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "size": len(content),
                    "archived": False,
                })

            # Now physically archive the ingest+archive pool only.
            for path in ingest_archive:
                rel = path.relative_to(ROOT).as_posix()
                target = ARCHIVE_DIR / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()
                shutil.move(str(path), str(target))
                # leave a small redirect pointer so anyone hitting the old path
                # is directed back to Studio.
                pointer = path
                pointer.write_text(
                    f"# Moved into Studio (sweep 2026-05-01)\n\n"
                    f"This file is now tracked in Studio as project_docs row\n"
                    f"`doc_name = {rel}` (Knowledge Center → search '{path.name}').\n"
                    f"Original snapshot: `{target.relative_to(ROOT).as_posix()}`.\n"
                    f"Edits should happen in Studio, not on disk.\n",
                    encoding="utf-8",
                )
                counts["archived"] += 1
                for m in manifest:
                    if m["source"] == rel:
                        m["archived"] = True
                        m["archive_path"] = target.relative_to(ROOT).as_posix()
    finally:
        conn.close()

    manifest_path = ARCHIVE_DIR / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "project": PROJECT,
                "sweep": "sweep-202605-01",
                "counts": counts,
                "items": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(counts, indent=2))
    print(f"manifest: {manifest_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
