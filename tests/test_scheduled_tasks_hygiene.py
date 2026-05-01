"""Tests for scheduled_tasks startup hygiene migration.

Covers PACKET-05 STEP S-642C4CC9B7 + S-57D0D9E5F3:
- Duplicate scheduled_tasks rows are deduped on startup.
- Enabled rows with NULL/empty next_run are backfilled.
- Migration is idempotent (running twice is a no-op).
- Migration never raises on a malformed legacy table.
"""
from __future__ import annotations

import sqlite3

import pytest

from utils.db._schema import _migrate_scheduled_tasks_hygiene


def _make_table(conn):
    conn.executescript(
        """
        CREATE TABLE scheduled_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            schedule    TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            action_data TEXT NOT NULL DEFAULT '',
            last_run    TEXT,
            next_run    TEXT,
            enabled     INTEGER DEFAULT 1
        );
        """
    )


def test_dedupe_keeps_latest_row_per_name():
    conn = sqlite3.connect(":memory:")
    _make_table(conn)
    conn.executemany(
        "INSERT INTO scheduled_tasks(name, schedule, next_run, enabled) VALUES (?, ?, ?, 1)",
        [
            ("daily-research", "0 6 * * *", "2026-05-02 06:00:00"),
            ("daily-research", "0 6 * * *", "2026-05-02 06:00:00"),
            ("daily-research", "0 6 * * *", "2026-05-03 06:00:00"),  # latest, keep
            ("backup-verify",  "30 4 * * *", "2026-05-02 04:30:00"),
        ],
    )
    conn.commit()

    stats = _migrate_scheduled_tasks_hygiene(conn)
    assert stats["duplicates_removed"] == 2

    rows = conn.execute(
        "SELECT name, COUNT(*) FROM scheduled_tasks GROUP BY name ORDER BY name"
    ).fetchall()
    assert rows == [("backup-verify", 1), ("daily-research", 1)]
    # Latest id (3) should have survived.
    survivor_id = conn.execute(
        "SELECT id FROM scheduled_tasks WHERE name='daily-research'"
    ).fetchone()[0]
    assert survivor_id == 3


def test_fills_missing_next_run_on_enabled():
    conn = sqlite3.connect(":memory:")
    _make_table(conn)
    conn.executemany(
        "INSERT INTO scheduled_tasks(name, schedule, next_run, enabled) VALUES (?, ?, ?, ?)",
        [
            ("alpha", "* * * * *", None, 1),    # missing → fill
            ("bravo", "* * * * *", "",  1),    # empty → fill
            ("charlie", "* * * * *", None, 0),  # disabled → leave alone
            ("delta", "* * * * *", "2026-05-02 06:00:00", 1),  # already set
        ],
    )
    conn.commit()

    stats = _migrate_scheduled_tasks_hygiene(conn)
    assert stats["next_run_filled"] == 2

    by_name = {
        row[0]: row[1]
        for row in conn.execute("SELECT name, next_run FROM scheduled_tasks").fetchall()
    }
    assert by_name["alpha"] and by_name["alpha"] != ""
    assert by_name["bravo"] and by_name["bravo"] != ""
    # Disabled row stays empty.
    assert (by_name["charlie"] or "") == ""
    # Already-set row is untouched.
    assert by_name["delta"] == "2026-05-02 06:00:00"


def test_idempotent_second_run_is_noop():
    conn = sqlite3.connect(":memory:")
    _make_table(conn)
    conn.executemany(
        "INSERT INTO scheduled_tasks(name, schedule, next_run, enabled) VALUES (?, ?, ?, 1)",
        [("dup", "* * * * *", "x"), ("dup", "* * * * *", "x")],
    )
    conn.commit()

    first = _migrate_scheduled_tasks_hygiene(conn)
    second = _migrate_scheduled_tasks_hygiene(conn)
    assert first["duplicates_removed"] == 1
    assert second == {"duplicates_removed": 0, "next_run_filled": 0}


def test_handles_malformed_legacy_table():
    """If the table is missing the expected columns, migration must not raise."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE scheduled_tasks (id INTEGER PRIMARY KEY)")
    conn.commit()
    stats = _migrate_scheduled_tasks_hygiene(conn)
    assert stats == {"duplicates_removed": 0, "next_run_filled": 0}


def test_blank_name_rows_are_left_alone():
    """Empty-name rows are allowed by the partial unique index — don't dedupe them."""
    conn = sqlite3.connect(":memory:")
    _make_table(conn)
    conn.executemany(
        "INSERT INTO scheduled_tasks(name, schedule, next_run, enabled) VALUES ('', ?, ?, 1)",
        [("a", "x"), ("b", "y"), ("c", "z")],
    )
    conn.commit()
    stats = _migrate_scheduled_tasks_hygiene(conn)
    assert stats["duplicates_removed"] == 0
    assert conn.execute("SELECT COUNT(*) FROM scheduled_tasks").fetchone()[0] == 3
