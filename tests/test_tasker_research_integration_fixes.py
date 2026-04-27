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
