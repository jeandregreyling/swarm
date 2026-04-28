import sqlite3


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            schedule TEXT,
            action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '',
            last_run TEXT,
            next_run TEXT,
            enabled INTEGER DEFAULT 1,
            created_by TEXT DEFAULT 'ghost',
            created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL
        )"""
    )
    return conn


def test_scheduler_add_task_is_idempotent_and_returns_id(tmp_path, monkeypatch):
    import fridays.scheduler as scheduler

    db_path = tmp_path / "scheduler.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(scheduler, "get_connection", get_conn)

    first = scheduler.add_task("example", "daily 09:00", "PYTHON", "housekeeping")
    second = scheduler.add_task("example", "daily 10:00", "PYTHON", "daily_digest")

    assert first == second
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM scheduled_tasks WHERE name='example'").fetchall()
    assert len(rows) == 1
    assert rows[0]["schedule"] == "daily 10:00"
    assert rows[0]["action_data"] == "daily_digest"
    assert rows[0]["next_run"]


def test_scheduler_check_due_passes_python_task_arguments(tmp_path, monkeypatch):
    import fridays.scheduler as scheduler
    import fridays.task_runner as task_runner

    db_path = tmp_path / "due.db"
    calls = []

    def get_conn():
        return _connect(db_path)

    def fake_run_task(name, args=""):
        calls.append((name, args))
        return True, "ok"

    monkeypatch.setattr(scheduler, "get_connection", get_conn)
    monkeypatch.setattr(task_runner, "run_task", fake_run_task)

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scheduled_tasks
               (name, schedule, action_type, action_data, next_run, enabled)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (
                "watched",
                "daily 06:30",
                "PYTHON",
                'interest_research_update topic="SAP payroll Australia" depth=standard',
                "2000-01-01 00:00:00",
            ),
        )

    scheduler.check_due()

    assert calls == [
        (
            "interest_research_update",
            "'topic=SAP payroll Australia' depth=standard",
        )
    ]


def test_tasker_run_skill_passes_arguments(monkeypatch):
    import fridays.skills as skills
    import fridays.task_runner as task_runner

    calls = []

    def fake_run_task(name, args=""):
        calls.append((name, args))
        return True, "ok"

    monkeypatch.setattr(task_runner, "run_task", fake_run_task)

    ok, msg = skills._skill_tasker_run(
        'interest_research_update topic="SAP payroll Australia" depth=quick',
        "seven",
    )

    assert ok is True
    assert msg == "ok"
    assert calls == [
        (
            "interest_research_update",
            "'topic=SAP payroll Australia' depth=quick",
        )
    ]


def test_relay_recovery_sweep_dry_run_reports_open_cards(monkeypatch):
    import fridays.task_runner as task_runner
    from utils.db import chat as db_chat

    monkeypatch.setattr(db_chat, "get_open_chat_relay_recoveries", lambda limit=3: [
        {"recovery_id": "recovery-a"},
        {"recovery_id": "recovery-b"},
    ])
    monkeypatch.setattr(task_runner, "_log_run", lambda *a, **k: None)

    ok, msg = task_runner.run_task("relay_recovery_sweep", args="limit=2")

    assert ok is True
    assert "2 open relay recoveries pending" in msg
    assert "run_agents=1" in msg


def test_relay_recovery_sweep_active_run_uses_leases(monkeypatch):
    import json
    import sys
    import types

    import fridays.task_runner as task_runner
    from utils.db import chat as db_chat

    leased = []
    updates = []
    messages = []

    def fake_lease(owner, limit=3, lease_seconds=1800, conversation_id=None):
        leased.append((owner, limit, lease_seconds, conversation_id))
        return [{
            "recovery_id": "recovery-active",
            "conversation_id": 99,
            "stalled_agent": "qwen",
            "summary": "active recovery",
            "relay_context_json": json.dumps({
                "thread_tail": [{"from_agent": "user", "to_agent": "qwen", "content": "continue this"}],
                "stage_trace": [{"text": "handoff stalled"}],
            }),
        }]

    monkeypatch.setattr(db_chat, "lease_chat_relay_recoveries", fake_lease)
    monkeypatch.setattr(
        db_chat,
        "update_chat_relay_recovery_status",
        lambda rid, status, summary=None: updates.append((rid, status, summary)) or True,
    )
    monkeypatch.setattr(db_chat, "log_message", lambda *args, **kwargs: messages.append((args, kwargs)))
    monkeypatch.setattr(task_runner, "_log_run", lambda *a, **k: None)
    monkeypatch.setitem(
        sys.modules,
        "orchestrator",
        types.SimpleNamespace(ask_agent=lambda agent, prompt: f"{agent} reviewed"),
    )

    ok, msg = task_runner.run_task("relay_recovery_sweep", args="limit=1 run_agents=1 lease_minutes=5 force=1")

    assert ok is True
    assert "Reviewed 1 relay recoveries: recovery-active" in msg
    assert leased == [("tasker:relay_recovery_sweep", 1, 300, None)]
    assert updates and updates[0][0] == "recovery-active"
    assert updates[0][1] == "reviewed"
    assert "librarian: librarian reviewed" in updates[0][2]
    assert len(messages) == 2


def test_relay_recovery_sweep_active_run_respects_idle_window(monkeypatch):
    import fridays.task_runner as task_runner
    from utils.db import chat as db_chat

    leased = []
    monkeypatch.setattr(db_chat, "lease_chat_relay_recoveries", lambda *a, **k: leased.append((a, k)) or [])
    monkeypatch.setattr(task_runner, "_log_run", lambda *a, **k: None)
    monkeypatch.setattr(task_runner, "_tasker_in_idle_window", lambda window: False)

    ok, msg = task_runner.run_task("relay_recovery_sweep", args="limit=1 run_agents=1 idle_window=22:00-06:00")

    assert ok is True
    assert "deferred outside idle window 22:00-06:00" in msg
    assert "force=1" in msg
    assert leased == []


def test_research_quick_api_creates_single_session(monkeypatch):
    from flask import Flask

    import frontend.blueprints.research as research_bp

    calls = []

    def fake_run_research(topic, *, depth="standard", requesting_agent="user"):
        calls.append((topic, depth, requesting_agent))
        return 42, "summary"

    monkeypatch.setattr("fridays.research_workflow.run_research", fake_run_research)

    app = Flask(__name__)
    app.register_blueprint(research_bp.research_bp)
    client = app.test_client()

    resp = client.post(
        "/api/research/start",
        json={"topic": "integration", "depth": "quick", "agent": "seven"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["session_id"] == 42
    assert calls == [("integration", "quick", "seven")]
