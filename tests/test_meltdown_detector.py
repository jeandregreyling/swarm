"""Tests for utils/meltdown_detector.py.

All tests use monkeypatch — no real system calls or DB mutations.
"""
from __future__ import annotations

import sqlite3

import pytest

from utils.meltdown_detector import check, heal


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "tasks.db"


@pytest.fixture
def db_conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE scheduled_tasks (
            name TEXT PRIMARY KEY,
            next_run TEXT,
            action_type TEXT,
            enabled INTEGER DEFAULT 1
        )
        """
    )
    conn.commit()
    return conn


def test_check_healthy_when_all_clear(monkeypatch):
    monkeypatch.setattr("utils.meltdown_detector._load_average", lambda: 2.0)
    monkeypatch.setattr("utils.meltdown_detector._ollama_runner_pids", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._systemd_restart_counts", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._stale_scheduled_tasks", lambda conn=None: [])
    monkeypatch.setattr("utils.meltdown_detector._dev_uat_background_threads", lambda: [])

    r = check()
    assert r["ok"] is True
    assert r["severity"] == "healthy"
    assert r["findings"] == []


def test_check_critical_on_high_load(monkeypatch):
    monkeypatch.setattr("utils.meltdown_detector._load_average", lambda: 30.0)
    monkeypatch.setattr("utils.meltdown_detector._ollama_runner_pids", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._systemd_restart_counts", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._stale_scheduled_tasks", lambda conn=None: [])
    monkeypatch.setattr("utils.meltdown_detector._dev_uat_background_threads", lambda: [])

    r = check()
    assert r["ok"] is False
    assert r["severity"] == "critical"
    assert any(f["kind"] == "high_load" for f in r["findings"])


def test_check_critical_on_ollama_runaway(monkeypatch):
    monkeypatch.setattr("utils.meltdown_detector._load_average", lambda: 5.0)
    monkeypatch.setattr(
        "utils.meltdown_detector._ollama_runner_pids",
        lambda: [{"pid": "12345", "cpu_percent": 350.0, "line": "fake"}],
    )
    monkeypatch.setattr("utils.meltdown_detector._systemd_restart_counts", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._stale_scheduled_tasks", lambda conn=None: [])
    monkeypatch.setattr("utils.meltdown_detector._dev_uat_background_threads", lambda: [])

    r = check()
    assert r["ok"] is False
    assert r["severity"] == "critical"
    assert any(f["kind"] == "ollama_runaway" for f in r["findings"])


def test_check_critical_on_restart_loop(monkeypatch):
    monkeypatch.setattr("utils.meltdown_detector._load_average", lambda: 5.0)
    monkeypatch.setattr("utils.meltdown_detector._ollama_runner_pids", lambda: [])
    monkeypatch.setattr(
        "utils.meltdown_detector._systemd_restart_counts",
        lambda: [{"service": "swarm-discord.service", "restarts": 42}],
    )
    monkeypatch.setattr("utils.meltdown_detector._stale_scheduled_tasks", lambda conn=None: [])
    monkeypatch.setattr("utils.meltdown_detector._dev_uat_background_threads", lambda: [])

    r = check()
    assert r["ok"] is False
    assert r["severity"] == "critical"
    assert any(f["kind"] == "restart_loop" for f in r["findings"])


def test_check_warning_on_stale_task(monkeypatch, db_conn):
    old = "2026-01-01 00:00:00"
    db_conn.execute(
        "INSERT INTO scheduled_tasks (name, next_run, action_type, enabled) VALUES (?, ?, ?, 1)",
        ("zombie_task", old, "PYTHON"),
    )
    db_conn.commit()

    monkeypatch.setattr("utils.meltdown_detector._load_average", lambda: 5.0)
    monkeypatch.setattr("utils.meltdown_detector._ollama_runner_pids", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._systemd_restart_counts", lambda: [])
    monkeypatch.setattr(
        "utils.meltdown_detector._stale_scheduled_tasks",
        lambda conn=None: [{"name": "zombie_task", "next_run": old, "action_type": "PYTHON"}],
    )
    monkeypatch.setattr("utils.meltdown_detector._dev_uat_background_threads", lambda: [])

    r = check()
    assert r["ok"] is False
    assert r["severity"] == "warning"
    assert any(f["kind"] == "stale_task" for f in r["findings"])


def test_heal_disables_stale_task(monkeypatch, db_conn, db_path):
    old = "2026-01-01 00:00:00"
    db_conn.execute(
        "INSERT INTO scheduled_tasks (name, next_run, action_type, enabled) VALUES (?, ?, ?, 1)",
        ("zombie_task", old, "PYTHON"),
    )
    db_conn.commit()
    db_conn.close()  # done with setup connection

    def _new_conn():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("utils.meltdown_detector._load_average", lambda: 5.0)
    monkeypatch.setattr("utils.meltdown_detector._ollama_runner_pids", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._systemd_restart_counts", lambda: [])
    monkeypatch.setattr(
        "utils.meltdown_detector._stale_scheduled_tasks",
        lambda conn=None: [{"name": "zombie_task", "next_run": old, "action_type": "PYTHON"}],
    )
    monkeypatch.setattr("utils.meltdown_detector._dev_uat_background_threads", lambda: [])
    monkeypatch.setattr(
        "utils.meltdown_detector._run",
        lambda cmd, timeout=5.0: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr("utils.db._connection.get_connection", _new_conn)

    report = check()
    result = heal(report)
    assert any("disabled stale scheduled task" in a for a in result["actions"])

    fresh = sqlite3.connect(str(db_path))
    fresh.row_factory = sqlite3.Row
    row = fresh.execute(
        "SELECT enabled FROM scheduled_tasks WHERE name=?", ("zombie_task",)
    ).fetchone()
    assert row["enabled"] == 0
    fresh.close()


def test_heal_noop_when_healthy(monkeypatch):
    monkeypatch.setattr("utils.meltdown_detector._load_average", lambda: 2.0)
    monkeypatch.setattr("utils.meltdown_detector._ollama_runner_pids", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._systemd_restart_counts", lambda: [])
    monkeypatch.setattr("utils.meltdown_detector._stale_scheduled_tasks", lambda conn=None: [])
    monkeypatch.setattr("utils.meltdown_detector._dev_uat_background_threads", lambda: [])

    result = heal()
    assert result["ok"] is True
    assert result["actions"] == []
    assert result["original_severity"] == "healthy"
