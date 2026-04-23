"""core.knowledge.scripts — Knowledge Center's test-lab script registry.

Session 29.2: Knowledge Center now owns the concept of "what test scripts
exist". This module currently re-exports the shape from
``core.testlab_registry`` so callers can migrate to the KC namespace
without the registry data physically moving yet.

Also adds ``record_change_run`` / ``list_change_runs`` — lightweight
persistence for per-change script selection so the UI can remember which
scripts a user ran for a given change_id.

Table (auto-created lazily):
    change_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        change_id TEXT NOT NULL,
        script_ids TEXT NOT NULL,          -- JSON array of ids
        created_at REAL NOT NULL           -- unix ts
    )
"""
from __future__ import annotations

import json
import time
from typing import Dict, Iterable, List, Optional

from core import testlab_registry as _legacy

__all__ = [
    'get_registry', 'get_entry',
    'record_change_run', 'list_change_runs',
]

# ── Registry (re-export) ───────────────────────────────────────────────────

def get_registry() -> List[Dict]:
    """Return the full script registry (list of dicts)."""
    return _legacy.get_registry()


def get_entry(script_id: str) -> Optional[Dict]:
    """Return a single registry entry by id, or None."""
    return _legacy.get_entry(script_id)


# ── Change-run history ────────────────────────────────────────────────────

_SCHEMA_READY = False


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS change_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_id TEXT NOT NULL,
                script_ids TEXT NOT NULL,
                created_at REAL NOT NULL
            )""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_change_runs_change_id "
                "ON change_runs(change_id)"
            )
            conn.commit()
        finally:
            conn.close()
        _SCHEMA_READY = True
    except Exception:
        # best-effort — DB unavailable is not fatal, KC still works read-only
        pass


def record_change_run(change_id: str, script_ids: Iterable[str]) -> bool:
    """Persist the set of scripts selected for a change. Best-effort.

    Returns True on insert, False on any failure.
    """
    if not change_id:
        return False
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO change_runs (change_id, script_ids, created_at) VALUES (?, ?, ?)",
                (str(change_id)[:128], json.dumps(list(script_ids)), time.time()),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def list_change_runs(change_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Return recent change-run rows, most-recent first. Best-effort."""
    _ensure_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            if change_id:
                rows = conn.execute(
                    "SELECT id, change_id, script_ids, created_at FROM change_runs "
                    "WHERE change_id=? ORDER BY id DESC LIMIT ?",
                    (str(change_id)[:128], int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, change_id, script_ids, created_at FROM change_runs "
                    "ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    out: List[Dict] = []
    for r in rows:
        try:
            ids = json.loads(r['script_ids'])
        except Exception:
            ids = []
        out.append({
            'id': r['id'],
            'change_id': r['change_id'],
            'script_ids': ids,
            'created_at': r['created_at'],
        })
    return out
