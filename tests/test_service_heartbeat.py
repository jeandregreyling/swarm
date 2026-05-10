"""Tests for utils/service_heartbeat.py.

Covers:
- record_startup increments restart_count and creates rows.
- record_beat updates last_beat_at.
- warnings() flags stale heartbeats and frequent restarts.

All tests use tmp_path — no production DB is touched.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from utils.service_heartbeat import record_beat, record_startup, warnings


@pytest.fixture
def conn(tmp_path):
    """Fresh in-memory SQLite with the service_heartbeat schema."""
    db_path = tmp_path / "heartbeat.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE service_heartbeat (
            service_name TEXT PRIMARY KEY,
            code_version TEXT,
            started_at TEXT,
            last_beat_at TEXT,
            pid INTEGER,
            restart_count INTEGER DEFAULT 0,
            last_restart_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def test_record_startup_creates_row(conn, monkeypatch):
    monkeypatch.setattr(
        "utils.service_heartbeat._conn", lambda: conn
    )
    monkeypatch.setattr(
        "utils.service_heartbeat._git_short_sha", lambda: "abc123"
    )
    monkeypatch.setattr("os.getpid", lambda: 42)

    record_startup("test-svc", code_version="v1")
    row = conn.execute(
        "SELECT * FROM service_heartbeat WHERE service_name=?", ("test-svc",)
    ).fetchone()
    assert row is not None
    assert row["code_version"] == "v1"
    assert row["pid"] == 42
    assert row["restart_count"] == 0


def test_record_startup_increments_restart_count(conn, monkeypatch):
    monkeypatch.setattr("utils.service_heartbeat._conn", lambda: conn)
    monkeypatch.setattr("utils.service_heartbeat._git_short_sha", lambda: "abc123")
    monkeypatch.setattr("os.getpid", lambda: 99)

    record_startup("loop-svc")
    record_startup("loop-svc")
    record_startup("loop-svc")

    row = conn.execute(
        "SELECT restart_count FROM service_heartbeat WHERE service_name=?",
        ("loop-svc",),
    ).fetchone()
    assert row["restart_count"] == 2


def test_record_beat_updates_timestamp(conn, monkeypatch):
    monkeypatch.setattr("utils.service_heartbeat._conn", lambda: conn)
    monkeypatch.setattr("utils.service_heartbeat._git_short_sha", lambda: "abc123")

    record_startup("beat-svc")
    before = conn.execute(
        "SELECT last_beat_at FROM service_heartbeat WHERE service_name=?",
        ("beat-svc",),
    ).fetchone()["last_beat_at"]

    import time
    time.sleep(1.1)
    record_beat("beat-svc")
    after = conn.execute(
        "SELECT last_beat_at FROM service_heartbeat WHERE service_name=?",
        ("beat-svc",),
    ).fetchone()["last_beat_at"]

    assert after != before


def test_warnings_flags_frequent_restarts(conn, monkeypatch):
    monkeypatch.setattr("utils.service_heartbeat._conn", lambda: conn)
    monkeypatch.setattr("utils.service_heartbeat._git_short_sha", lambda: "abc123")

    # Simulate a service that has restarted 5 times
    for _ in range(5):
        record_startup("noisy-svc")

    w = warnings(stale_minutes=5, restart_threshold=3)
    restart_alerts = [x for x in w if x["kind"] == "frequent_restarts"]
    assert len(restart_alerts) == 1
    assert restart_alerts[0]["service"] == "noisy-svc"
    assert restart_alerts[0]["restart_count"] == 4


def test_warnings_flags_stale_heartbeat(conn, monkeypatch):
    monkeypatch.setattr("utils.service_heartbeat._conn", lambda: conn)
    monkeypatch.setattr("utils.service_heartbeat._git_short_sha", lambda: "abc123")

    old = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO service_heartbeat
        (service_name, code_version, started_at, last_beat_at, pid, restart_count, last_restart_at)
        VALUES (?, 'v1', ?, ?, 1, 0, '')
        """,
        ("stale-svc", old, old),
    )
    conn.commit()

    w = warnings(stale_minutes=5, restart_threshold=999)
    stale_alerts = [x for x in w if x["kind"] == "stale_heartbeat"]
    assert len(stale_alerts) == 1
    assert stale_alerts[0]["service"] == "stale-svc"
    assert stale_alerts[0]["minutes_since_beat"] >= 10.0


def test_warnings_empty_when_healthy(conn, monkeypatch):
    monkeypatch.setattr("utils.service_heartbeat._conn", lambda: conn)
    monkeypatch.setattr("utils.service_heartbeat._git_short_sha", lambda: "abc123")

    record_startup("healthy-svc")
    w = warnings(stale_minutes=5, restart_threshold=10)
    assert w == []
