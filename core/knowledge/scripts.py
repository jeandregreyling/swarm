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
    'seed_registry_to_db', 'list_scripts_db',
    'timeline_for_change',
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


# ── Session 30 — DB-backed script registry (MD-SESSION30-EB84C987D775) ────
#
# Until now ``get_registry()`` re-exported the module-level REGISTRY from
# ``core.testlab_registry``. The DB-backed variant lets operators seed/edit
# scripts at runtime (admin UI, future "user-defined scripts") while keeping
# the file-level REGISTRY as the deterministic seed + fallback.

_DB_SCHEMA_READY = False


def _ensure_db_schema() -> None:
    global _DB_SCHEMA_READY
    if _DB_SCHEMA_READY:
        return
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_scripts (
                id TEXT PRIMARY KEY,
                grp TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT,
                command TEXT NOT NULL,
                change_aware INTEGER NOT NULL DEFAULT 0,
                default_on INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'seed',
                updated_at REAL NOT NULL
            )""")
            conn.commit()
        finally:
            conn.close()
        _DB_SCHEMA_READY = True
    except Exception:
        pass


def seed_registry_to_db(*, force: bool = False) -> int:
    """Idempotently push the file-level REGISTRY rows into knowledge_scripts.

    Returns the number of rows written. ``force=True`` overwrites existing
    rows; otherwise existing ids are preserved (so user edits survive seeds).
    """
    _ensure_db_schema()
    written = 0
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            for entry in _legacy.get_registry():
                sid = str(entry.get('id') or '').strip()
                if not sid:
                    continue
                if not force:
                    row = conn.execute(
                        "SELECT 1 FROM knowledge_scripts WHERE id=?", (sid,)
                    ).fetchone()
                    if row:
                        continue
                conn.execute(
                    "INSERT OR REPLACE INTO knowledge_scripts "
                    "(id, grp, label, description, command, change_aware, default_on, source, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sid,
                        str(entry.get('group') or 'misc'),
                        str(entry.get('label') or sid),
                        str(entry.get('description') or ''),
                        str(entry.get('command') or ''),
                        1 if entry.get('change_aware') else 0,
                        1 if entry.get('default_on') else 0,
                        'seed',
                        time.time(),
                    ),
                )
                written += 1
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
    return written


def list_scripts_db() -> List[Dict]:
    """Return all knowledge_scripts rows in registry-shape. Falls back to the
    file-level REGISTRY when the DB is unavailable or empty."""
    _ensure_db_schema()
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.row_factory = sqlite3_row()
            rows = conn.execute(
                "SELECT id, grp, label, description, command, change_aware, "
                "default_on, source, updated_at FROM knowledge_scripts "
                "ORDER BY grp, label"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []
    if not rows:
        return _legacy.get_registry()
    out: List[Dict] = []
    for r in rows:
        out.append({
            'id': r['id'],
            'group': r['grp'],
            'label': r['label'],
            'description': r['description'] or '',
            'command': r['command'],
            'change_aware': bool(r['change_aware']),
            'default_on': bool(r['default_on']),
            'source': r['source'],
            'updated_at': r['updated_at'],
        })
    return out


def sqlite3_row():
    import sqlite3 as _s
    return _s.Row


# ── Session 30 — Step-through timeline (MD-SESSION30-CB0CE94C6B60) ────────


def timeline_for_change(change_id: str, *, limit: int = 200) -> List[Dict]:
    """Return a unified, time-ordered timeline for a change_id.

    Stitches together two sources:
      * ``change_runs`` — script-selection events (which scripts the user
        chose to run for this change).
      * ``test_runs``   — actual run lifecycle (started/finished, status).

    Each item has ``ts`` (unix seconds), ``kind`` and source-specific fields.
    Ordered oldest → newest so a UI can render a left-to-right timeline.
    """
    cid = str(change_id or '').strip()
    if not cid:
        return []
    items: List[Dict] = []

    # change_runs side
    try:
        for row in list_change_runs(change_id=cid, limit=limit):
            items.append({
                'kind': 'change_run',
                'ts': row.get('created_at'),
                'change_run_id': row.get('id'),
                'change_id': row.get('change_id'),
                'script_ids': row.get('script_ids') or [],
            })
    except Exception:
        pass

    # test_runs side — use the shared list_runs() if available
    try:
        from core.knowledge import test_runs as _tr
        for run in _tr.list_runs(change_id=cid, limit=limit) or []:
            items.append({
                'kind': 'test_run',
                'ts': run.get('started_at') or run.get('created_at') or 0,
                'run_id': run.get('id') or run.get('run_id'),
                'script_id': run.get('script_id'),
                'status': run.get('status'),
                'finished_at': run.get('finished_at'),
                'exit_code': run.get('exit_code'),
                'triggered_by': run.get('triggered_by'),
            })
    except Exception:
        pass

    items.sort(key=lambda x: (x.get('ts') or 0))
    return items[:limit]
