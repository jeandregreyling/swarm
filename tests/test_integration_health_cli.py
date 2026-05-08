"""Tests for ops.integration_health and ops.service_log_summary CLIs.

Covers PACKET-05:
  * S-55BD504D26 (preflight Make target)
  * S-C67446BD44 (integration health CLI)
  * S-6D75823AEC (service log summarizer)
"""
from __future__ import annotations

import io
import json
import sqlite3
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import ops.integration_health as ih
import ops.service_log_summary as ls


def _seed_db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            schedule TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            action_data TEXT NOT NULL DEFAULT '',
            last_run TEXT,
            next_run TEXT,
            enabled INTEGER DEFAULT 1
        );
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0,
            details_json TEXT DEFAULT ''
        );
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT,
            description TEXT,
            status TEXT,
            owner TEXT,
            order_idx INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO scheduled_tasks(name, schedule, next_run, enabled) VALUES (?, ?, ?, ?)",
        [
            ("good-task", "* * * * *", "2099-01-01 00:00:00", 1),
            ("missing-next", "* * * * *", None, 1),
            ("dup", "* * * * *", "x", 1),
            ("dup", "* * * * *", "x", 1),
        ],
    )
    conn.executemany(
        "INSERT INTO task_run_log(task_name, status, started_at, details_json) VALUES (?, ?, ?, ?)",
        [
            ("good-task", "ok", "2026-05-02 06:00:00", "{}"),
            ("dup", "error", "2026-05-02 06:01:00", '{"err":"boom"}'),
        ],
    )
    conn.executemany(
        "INSERT INTO project_steps(step_id, project_id, status, order_idx) VALUES (?, ?, ?, ?)",
        [("S-A", "P-X", "todo", 0), ("S-B", "P-X", "done", 1)],
    )
    conn.commit()
    conn.close()


def test_db_health_detects_dupes_and_missing_next_run(tmp_path, monkeypatch):
    db = tmp_path / "swarm.db"
    _seed_db(db)
    monkeypatch.setattr(ih, "DB_PATH", str(db))
    snap = ih.db_health()
    assert snap["ok"] is True
    assert snap["scheduled_tasks_total"] == 4
    assert snap["scheduled_tasks_missing_next_run"] == 1
    assert any(d["name"] == "dup" for d in snap["duplicates"])
    assert snap["project_steps_open"] == 1
    assert snap["project_steps_done"] == 1
    assert any("missing next_run" in m for m in snap["issues"])


def test_db_health_handles_missing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ih, "DB_PATH", str(tmp_path / "nope.db"))
    snap = ih.db_health()
    assert snap["ok"] is False
    assert any("db not found" in m for m in snap["issues"])


def test_recent_failures_returns_only_errors(tmp_path, monkeypatch):
    db = tmp_path / "swarm.db"
    _seed_db(db)
    monkeypatch.setattr(ih, "DB_PATH", str(db))
    rows = ih.recent_failures()
    assert len(rows) == 1
    assert rows[0]["task"] == "dup"
    assert rows[0]["status"] == "error"


def test_route_imports_all_blueprints_load():
    snap = ih.route_imports()
    assert snap["ok"] is True, f"failed: {snap['failed']}"
    assert snap["modules"] > 10


def test_collect_returns_full_snapshot(tmp_path, monkeypatch):
    db = tmp_path / "swarm.db"
    _seed_db(db)
    monkeypatch.setattr(ih, "DB_PATH", str(db))
    # Stub services to avoid systemctl in tests.
    monkeypatch.setattr(ih, "service_status", lambda: [{"name": "x", "active": "active", "enabled": "enabled"}])
    snap = ih.collect()
    for key in ("db", "due_tasks", "services", "routes", "recent_failures", "issues", "overall_ok"):
        assert key in snap


def test_main_json_mode(tmp_path, monkeypatch, capsys):
    db = tmp_path / "swarm.db"
    _seed_db(db)
    monkeypatch.setattr(ih, "DB_PATH", str(db))
    monkeypatch.setattr(ih, "service_status", lambda: [])
    rc = ih.main(["--json"])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "db" in parsed and "issues" in parsed
    assert isinstance(rc, int)


def test_main_text_mode(tmp_path, monkeypatch, capsys):
    db = tmp_path / "swarm.db"
    _seed_db(db)
    monkeypatch.setattr(ih, "DB_PATH", str(db))
    monkeypatch.setattr(ih, "service_status", lambda: [])
    ih.main([])
    out = capsys.readouterr().out
    assert "Swarm integration health" in out
    assert "scheduled_tasks:" in out


def test_log_summary_collect_no_journalctl(monkeypatch):
    monkeypatch.setattr(ls.shutil, "which", lambda _name: None)
    snap = ls.collect("1h")
    assert snap["total_error_lines"] == 0
    assert snap["overall_ok"] is True
    assert all(unit["error_count"] == 0 for unit in snap["units"])


def test_log_summary_filters_only_error_lines(monkeypatch):
    sample = "INFO booted ok\nERROR something blew up\nDEBUG noise\nWARN latency rising\n"

    class _FakeProc:
        returncode = 0
        stdout = sample

    monkeypatch.setattr(ls.shutil, "which", lambda _name: "/usr/bin/journalctl")
    monkeypatch.setattr(
        ls.subprocess,
        "run",
        lambda *a, **k: _FakeProc(),
    )
    lines = ls.journal_lines("swarm-terminal", since="1h")
    assert any("ERROR" in line for line in lines)
    assert not any(line.startswith("INFO") for line in lines)


def test_log_summary_render_text():
    snap = {
        "generated_at": "now",
        "since": "1h",
        "total_error_lines": 1,
        "overall_ok": False,
        "units": [
            {"name": "swarm-terminal", "error_count": 1, "tail": ["ERROR boom"]},
            {"name": "swarm-listener", "error_count": 0, "tail": []},
        ],
    }
    text = ls.render_text(snap)
    assert "swarm-terminal" in text
    assert "ERROR boom" in text
    assert "swarm-listener" in text
    assert "clean" in text


def test_makefile_has_preflight_target():
    src = Path("Makefile").read_text(encoding="utf-8")
    assert "preflight:" in src
    assert "ops.integration_health" in src
    assert "integ-health:" in src
    assert "log-summary:" in src
