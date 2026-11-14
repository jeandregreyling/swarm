"""Service account storage initialization.

This module provides a lightweight SQLite3 schema for storing service principals
and their associated memory blobs.  The tables are intentionally minimal and
do not enforce any authentication or authorization logic beyond the
``role`` column.  Service principals are created with ``role='service'`` and
are initially disabled (``enabled=0``) until a scoped authentication
mechanism is implemented.

The ``service_memory`` table is not an authentication boundary; it merely
provides a partitioned storage area for each principal.
"""

import time
import sqlite3
from typing import Iterable

__all__ = ["initialise"]


def initialise(conn: sqlite3.Connection) -> None:
    """Create service account tables and seed built-in principals.

    Parameters
    ----------
    conn:
        A SQLite3 connection.  The caller owns the transaction; this
        function performs only ``CREATE TABLE`` and ``INSERT OR IGNORE``
        statements and does not commit.
    """
    # Create tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS service_principals (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role='service'),
            enabled INTEGER NOT NULL CHECK(enabled IN(0,1)),
            created_at REAL NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS service_memory (
            id INTEGER PRIMARY KEY,
            principal_id TEXT NOT NULL REFERENCES service_principals(id),
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            source_receipt TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )

    # Seed principals
    now = time.time()
    principals: Iterable[tuple[str, str]] = [
        ("apex", "APEX"),
        ("copilot-instructor", "VS Code Instructor"),
        ("gemini-advisor", "Gemini Advisor"),
        ("codex-instructor", "Codex"),
        ("tiered-assistant", "Tiered Model Assistant"),
        ("mistral-vibe", "Mistral Vibe"),
        ("claude-code", "Claude Code"),
    ]
    for pid, name in principals:
        conn.execute(
            """
            INSERT OR IGNORE INTO service_principals (
                id, display_name, role, enabled, created_at
            ) VALUES (?, ?, 'service', 0, ?);
            """,
            (pid, name, now),
        )
