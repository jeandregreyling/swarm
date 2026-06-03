from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_name TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            tags TEXT DEFAULT 'all'
        );
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            source_type TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            chunk_text TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS swarm_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            content TEXT NOT NULL,
            source_agent TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'fact',
            importance INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT '',
            subject TEXT DEFAULT '',
            content TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 5,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_qwen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'qwen',
            subject TEXT DEFAULT '',
            content TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 5,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'ghost',
            topic TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'user',
            score REAL DEFAULT 10.0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            source_agent TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS watched_topic_settings (
            topic_key TEXT PRIMARY KEY,
            cadence_minutes INTEGER DEFAULT 1440
        );
        CREATE TABLE IF NOT EXISTS watched_topic_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_key TEXT NOT NULL,
            topic TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            qualified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS research_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            status TEXT DEFAULT 'done',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS research_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            title TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS newsletter_article_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evidence_id INTEGER,
            vote TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            schedule TEXT,
            action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '',
            last_run TEXT,
            next_run TEXT,
            enabled INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL
        );
        """
    )
    return conn


def _hive_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hive_nodes (
            node_id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            enrolled_ts INTEGER NOT NULL,
            last_seen_ts INTEGER,
            telemetry_json TEXT,
            policy_json TEXT,
            label TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS hive_jobs (
            job_id TEXT PRIMARY KEY,
            node_id TEXT,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            result_json TEXT,
            created_ts INTEGER NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO hive_nodes (node_id, platform, enrolled_ts, last_seen_ts) VALUES (?,?,?,?)",
        ("potato-2", "android", 100, 1780595990),
    )
    conn.commit()
    conn.close()


def test_brain_health_flags_stale_newsletter_and_scheduler(tmp_path):
    from frontend.blueprints.kc_overview import build_brain_health

    db = tmp_path / "brain.db"
    hive = tmp_path / "hive.db"
    _hive_db(hive)
    conn = _connect(db)
    try:
        conn.execute(
            "INSERT INTO project_docs (doc_name, content, tags, updated_at) VALUES (?,?,?,?)",
            ("MONEY_HUB_DAILY_NEWSLETTER_2026-05-27.md", "old", "newsletter", "2026-05-27 07:00:00"),
        )
        conn.execute(
            "INSERT INTO swarm_knowledge (key, content, updated_at) VALUES (?,?,?)",
            ("newsletter-old", "old", "2026-05-27 07:00:00"),
        )
        conn.execute("INSERT INTO memory (agent, subject, content) VALUES ('qwen','note','remember this')")
        conn.execute("INSERT INTO user_interests (username, topic, source, active) VALUES ('ghost','SAP payroll Australia','agent',1)")
        conn.execute("INSERT INTO watched_topic_settings (topic_key) VALUES ('sap_payroll_australia')")
        conn.execute(
            "INSERT INTO watched_topic_evidence (topic_key, topic, evidence_fingerprint, updated_at) VALUES (?,?,?,?)",
            ("sap_payroll_australia", "SAP payroll Australia", "fp1", "2026-05-27 07:00:00"),
        )
        conn.execute(
            "INSERT INTO scheduled_tasks (name, schedule, action_type, action_data, next_run, enabled) VALUES (?,?,?,?,?,1)",
            ("money_hub_daily_newsletter", "daily 07:20", "PYTHON", "money_hub_daily_newsletter", "2026-05-28 07:20:00"),
        )
        conn.commit()

        data = build_brain_health(conn, hive_db_path=str(hive), now=datetime(2026, 6, 4, 8, 0, 0))

        assert data["status"] == "warn"
        areas = {f["area"] for f in data["findings"]}
        assert "newsletter" in areas
        assert "scheduler" in areas
        assert "interests" in areas
        assert data["checks"]["scheduler"]["stale_enabled_task_count"] == 1
        assert data["checks"]["hive"]["live_nodes"] == 1
    finally:
        conn.close()


def test_brain_health_endpoint_uses_registered_blueprint(tmp_path, monkeypatch):
    import frontend.blueprints.kc_overview as kc

    db = tmp_path / "brain-endpoint.db"
    hive = tmp_path / "hive-endpoint.db"
    _hive_db(hive)
    conn = _connect(db)
    conn.execute("INSERT INTO project_docs (doc_name, content, tags, updated_at) VALUES ('TODAY.md','ok','all','2026-06-04 07:00:00')")
    conn.execute("INSERT INTO knowledge_chunks (source_id, chunk_text) VALUES (1,'chunk')")
    conn.execute("INSERT INTO swarm_knowledge (key, content, updated_at) VALUES ('fact','ok','2026-06-04 07:00:00')")
    conn.execute("INSERT INTO memory (agent, subject, content) VALUES ('qwen','note','ok')")
    conn.execute("INSERT INTO user_interests (username, topic, source, active) VALUES ('ghost','SAP payroll Australia','user',1)")
    conn.commit()
    conn.close()

    def factory():
        return _connect(db)

    monkeypatch.setattr(kc, "get_connection", factory)
    monkeypatch.setenv("SWARM_HIVE_DB", str(hive))

    app = Flask(__name__)
    app.register_blueprint(kc.kc_overview_bp)
    client = app.test_client()
    resp = client.get("/api/kc/brain/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["checks"]["counts"]["project_docs"] == 1


def test_brain_health_treats_sqlite_now_as_utc_for_freshness(tmp_path):
    from datetime import timedelta, timezone

    from frontend.blueprints.kc_overview import build_brain_health

    db = tmp_path / "brain-timezone.db"
    conn = _connect(db)
    try:
        conn.execute(
            "INSERT INTO project_docs (doc_name, content, tags, updated_at) VALUES (?,?,?,?)",
            ("MONEY_HUB_DAILY_NEWSLETTER_2026-06-04.md", "fresh", "newsletter", "2026-06-03 20:25:00"),
        )
        conn.commit()

        data = build_brain_health(
            conn,
            now=datetime(2026, 6, 4, 6, 25, 0, tzinfo=timezone(timedelta(hours=10))),
        )

        assert data["checks"]["newsletter"]["latest_age_hours"] == 0
        assert "newsletter" not in {f["area"] for f in data["findings"]}
    finally:
        conn.close()


def test_brain_health_tasker_warning_counts_execution_failures_only(tmp_path):
    from frontend.blueprints.kc_overview import build_brain_health

    db = tmp_path / "brain-tasker.db"
    conn = _connect(db)
    try:
        conn.execute(
            "INSERT INTO task_run_log (task_name, status, output, run_at) VALUES (?,?,?,?)",
            ("android_hive_probe_gate", "blocked", "adb unavailable", "2026-06-03 20:00:00"),
        )
        conn.execute(
            "INSERT INTO task_run_log (task_name, status, output, run_at) VALUES (?,?,?,?)",
            ("runtime_policy_simplification_slice", "partial", "manual follow-up", "2026-06-03 20:00:00"),
        )
        conn.commit()

        data = build_brain_health(conn, now=datetime(2026, 6, 4, 6, 0, 0))

        assert data["checks"]["tasker"]["failures_24h"] == 0
        assert "tasker" not in {f["area"] for f in data["findings"]}

        conn.execute(
            "INSERT INTO task_run_log (task_name, status, output, run_at) VALUES (?,?,?,?)",
            ("watched_topic", "timeout", "hung", "2026-06-03 20:01:00"),
        )
        conn.commit()
        data = build_brain_health(conn, now=datetime(2026, 6, 4, 6, 0, 0))
        assert data["checks"]["tasker"]["failures_24h"] == 1
        assert "tasker" in {f["area"] for f in data["findings"]}
    finally:
        conn.close()
    assert "hive" in data["checks"]
    assert isinstance(data["findings"], list)
