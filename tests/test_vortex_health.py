"""Tests for core.vortex_health probe.

Regression for STEP-VORTEX-UPDATING-HEALTH-20260430.
"""
import datetime as dt
import sqlite3

import pytest

from core import vortex_health


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def schema(conn):
    conn.executescript(
        """
        CREATE TABLE time_events (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            agent TEXT,
            action TEXT
        );
        CREATE TABLE checkpoints (
            id INTEGER PRIMARY KEY,
            label TEXT
        );
        """
    )
    return conn


class TestProbeHealthy:
    def test_recent_event_is_healthy(self, schema):
        now = dt.datetime(2026, 5, 2, 12, 0, 0)
        recent = (now - dt.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        schema.execute(
            "INSERT INTO time_events (timestamp, agent, action) VALUES (?,?,?)",
            (recent, "twelve", "checkpoint"),
        )
        snap = vortex_health.probe(schema, now=now)
        assert snap["status"] == "healthy"
        assert snap["ok"] is True
        assert snap["age_seconds"] is not None
        assert snap["age_seconds"] < 600
        assert snap["recovery_actions"] == []

    def test_event_with_iso_T_separator_parses(self, schema):
        now = dt.datetime(2026, 5, 2, 12, 0, 0)
        recent = (now - dt.timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S")
        schema.execute(
            "INSERT INTO time_events (timestamp, agent, action) VALUES (?,?,?)",
            (recent, "twelve", "x"),
        )
        snap = vortex_health.probe(schema, now=now)
        assert snap["status"] == "healthy"

    def test_healthy_banner_is_none(self, schema):
        now = dt.datetime(2026, 5, 2, 12, 0, 0)
        recent = now.strftime("%Y-%m-%d %H:%M:%S")
        schema.execute(
            "INSERT INTO time_events (timestamp, agent, action) VALUES (?,?,?)",
            (recent, "twelve", "x"),
        )
        snap = vortex_health.probe(schema, now=now)
        assert vortex_health.banner_text(snap) is None


class TestProbeStale:
    def test_old_event_is_stale(self, schema):
        now = dt.datetime(2026, 5, 2, 12, 0, 0)
        old = (now - dt.timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        schema.execute(
            "INSERT INTO time_events (timestamp, agent, action) VALUES (?,?,?)",
            (old, "twelve", "x"),
        )
        snap = vortex_health.probe(schema, now=now)
        assert snap["status"] == "stale"
        assert snap["ok"] is False
        assert snap["age_seconds"] >= 6 * 3600
        assert snap["recovery_actions"]

    def test_stale_banner_mentions_age(self, schema):
        now = dt.datetime(2026, 5, 2, 12, 0, 0)
        old = (now - dt.timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        schema.execute(
            "INSERT INTO time_events (timestamp, agent, action) VALUES (?,?,?)",
            (old, "twelve", "x"),
        )
        snap = vortex_health.probe(schema, now=now)
        banner = vortex_health.banner_text(snap)
        assert banner is not None
        assert "12h" in banner

    def test_custom_threshold_makes_recent_event_stale(self, schema):
        now = dt.datetime(2026, 5, 2, 12, 0, 0)
        recent = (now - dt.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        schema.execute(
            "INSERT INTO time_events (timestamp, agent, action) VALUES (?,?,?)",
            (recent, "twelve", "x"),
        )
        snap = vortex_health.probe(schema, now=now, stale_threshold_seconds=60)
        assert snap["status"] == "stale"

    def test_unparseable_timestamp_is_stale(self, schema):
        schema.execute(
            "INSERT INTO time_events (timestamp, agent, action) VALUES (?,?,?)",
            ("not-a-real-timestamp", "twelve", "x"),
        )
        snap = vortex_health.probe(schema)
        assert snap["status"] == "stale"


class TestProbeEmpty:
    def test_empty_table_is_empty(self, schema):
        snap = vortex_health.probe(schema)
        assert snap["status"] == "empty"
        assert snap["ok"] is False
        assert snap["event_count"] == 0
        assert snap["last_event_at"] is None
        assert snap["recovery_actions"]

    def test_empty_banner_text(self, schema):
        snap = vortex_health.probe(schema)
        assert "no events" in vortex_health.banner_text(snap).lower()


class TestProbeMissing:
    def test_no_schema_is_missing(self, conn):
        snap = vortex_health.probe(conn)
        assert snap["status"] == "missing"
        assert snap["ok"] is False
        assert snap["recovery_actions"]

    def test_none_connection_is_missing(self):
        snap = vortex_health.probe(None)
        assert snap["status"] == "missing"
        assert snap["recovery_actions"]

    def test_missing_banner_mentions_schema(self, conn):
        snap = vortex_health.probe(conn)
        banner = vortex_health.banner_text(snap)
        assert "schema" in banner.lower()


class TestCheckpointCount:
    def test_counts_rows(self, schema):
        schema.execute("INSERT INTO checkpoints (label) VALUES (?)", ("a",))
        schema.execute("INSERT INTO checkpoints (label) VALUES (?)", ("b",))
        schema.commit()
        snap = vortex_health.probe(schema)
        assert snap["checkpoint_count"] == 2

    def test_zero_when_table_missing(self, conn):
        snap = vortex_health.probe(conn)
        assert snap["checkpoint_count"] == 0


class TestSnapshotShape:
    def test_keys_always_present(self, conn):
        snap = vortex_health.probe(conn)
        for key in (
            "ok", "status", "last_event_at", "age_seconds",
            "stale_threshold_seconds", "recovery_actions",
            "checkpoint_count", "event_count",
        ):
            assert key in snap

    def test_threshold_passes_through(self, schema):
        snap = vortex_health.probe(schema, stale_threshold_seconds=42)
        assert snap["stale_threshold_seconds"] == 42

    def test_recovery_actions_are_strings(self, conn):
        snap = vortex_health.probe(conn)
        for action in snap["recovery_actions"]:
            assert isinstance(action, str) and action

    def test_does_not_raise_on_garbage_conn(self):
        class _Bad:
            def execute(self, *a, **kw):
                raise RuntimeError("nope")
        snap = vortex_health.probe(_Bad())
        assert snap["status"] == "missing"
