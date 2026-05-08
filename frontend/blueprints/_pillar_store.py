"""Shared storage helpers for the four wishlist pillars.

The pillars (cyber-security, financial, trading, business) each own a
single core table and expose CRUD + a tight summary the Seven agent can
consult. They all share the same DB path resolution and id/timestamp
conventions, so we keep that here instead of duplicating across four
blueprints.

Public surface intentionally small:
    - db_path()       active swarm DB path (env overrides honoured).
    - connect()       sqlite3.Connection with Row factory.
    - gen_id(prefix)  short uppercase id, prefix-stable.
    - now_ts()        float epoch seconds.
    - ensure_columns  defensive ALTER TABLE for forward-compatible schemas.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import time


def db_path() -> str:
    """Return active swarm DB path. Honours both env vars used elsewhere."""
    return (
        os.environ.get('SWARM_MEMORY_DB')
        or os.environ.get('SWARM_DB_PATH')
        or os.path.join(
            os.environ.get(
                'SWARM_ROOT',
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
            ),
            'swarm_memory.db',
        )
    )


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def gen_id(prefix: str) -> str:
    """Return a short uppercase id: PFX-XXXXXXXX (8 hex chars)."""
    return f"{prefix.upper()}-{secrets.token_hex(4).upper()}"


def now_ts() -> float:
    return time.time()


def ensure_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: dict[str, str],
) -> None:
    """Add missing columns if the table predates a schema bump.

    `columns` maps column_name -> SQL type (e.g. {'notes': 'TEXT'}).
    Safe to call repeatedly; existing columns are left alone.
    """
    try:
        existing = {row['name'] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return
    for name, sqltype in columns.items():
        if name not in existing:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}")
            except sqlite3.Error:
                # Column race or unsupported default — leave it; caller is
                # responsible for backfilling on next write.
                pass
