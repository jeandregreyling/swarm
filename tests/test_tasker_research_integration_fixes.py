import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    conn.execute(
        """CREATE TABLE IF NOT EXISTS research_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            depth TEXT NOT NULL DEFAULT 'standard',
            status TEXT NOT NULL DEFAULT 'planning',
            phases_json TEXT NOT NULL DEFAULT '[]',
            linked_proposal_id TEXT DEFAULT '',
            requesting_agent TEXT NOT NULL DEFAULT 'user',
            summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS research_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES research_sessions(id),
            source_url TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT 'web',
            title TEXT NOT NULL DEFAULT '',
            snippet TEXT NOT NULL DEFAULT '',
            confidence REAL DEFAULT 0.5,
            collecting_agent TEXT NOT NULL DEFAULT '',
            snippet_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'ghost',
            topic TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'user',
            source_agent TEXT DEFAULT '',
            score REAL DEFAULT 10.0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, topic)
        )"""
    )
    return conn


def _insert_research_session(conn, topic, *, depth="quick", status="done", summary="summary"):
    cur = conn.execute(
        """INSERT INTO research_sessions
           (topic, depth, status, summary, requesting_agent)
           VALUES (?, ?, ?, ?, 'eight')""",
        (topic, depth, status, summary),
    )
    return cur.lastrowid


def _insert_evidence(conn, session_id, *, source_url, title, snippet, snippet_hash):
    conn.execute(
        """INSERT INTO research_evidence
           (session_id, source_url, source_type, title, snippet, confidence,
            collecting_agent, snippet_hash)
           VALUES (?, ?, 'web', ?, ?, 0.8, 'seeker', ?)""",
        (session_id, source_url, title, snippet, snippet_hash),
    )


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


def test_relay_db_retry_retries_sqlite_locks(monkeypatch):
    import sqlite3

    from utils.db import chat as db_chat

    calls = []
    sleeps = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise sqlite3.OperationalError("database is locked")
        return "claimed"

    monkeypatch.setattr(db_chat.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert db_chat._with_relay_db_retry(flaky, attempts=4, base_delay=0.1) == "claimed"
    assert len(calls) == 3
    assert sleeps == [0.1, 0.2]


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


def test_relay_recovery_sweep_hands_off_after_support_timeout(monkeypatch):
    import json

    import fridays.task_runner as task_runner
    from utils.db import chat as db_chat

    updates = []
    messages = []
    jobs = []

    monkeypatch.setattr(db_chat, "lease_chat_relay_recoveries", lambda *args, **kwargs: [{
        "recovery_id": "recovery-timeout",
        "conversation_id": 2832,
        "stalled_agent": "mistral",
        "summary": "mistral timed out",
        "relay_context_json": json.dumps({
            "thread_tail": [{"from_agent": "user", "to_agent": "mistral", "content": "fix the watchdog warning"}],
            "stage_trace": [{"text": "mistral timed out"}],
        }),
    }])
    monkeypatch.setattr(
        db_chat,
        "update_chat_relay_recovery_status",
        lambda rid, status, summary=None: updates.append((rid, status, summary)) or True,
    )
    monkeypatch.setattr(db_chat, "log_message", lambda *args, **kwargs: messages.append((args, kwargs)))
    monkeypatch.setattr(task_runner, "_log_run", lambda *a, **k: None)
    monkeypatch.setattr(
        task_runner,
        "_ask_agent_with_timeout",
        lambda agent, prompt, timeout_seconds=240: (False, f"[{agent}] timed out"),
    )
    monkeypatch.setattr(
        task_runner,
        "_run_relay_handoff_agent",
        lambda agent, prompt, timeout_seconds=120: (True, "qwen completed the visible recovery\nDEOS_STATUS: done", 7),
    )
    monkeypatch.setattr(
        task_runner,
        "_record_relay_handoff_job",
        lambda *args, **kwargs: jobs.append((args, kwargs)) or "job-handoff",
    )

    ok, msg = task_runner.run_task(
        "relay_recovery_sweep",
        args="limit=1 run_agents=1 agents=librarian lease_minutes=5 force=1 handoff_agents=qwen,gemma",
    )

    assert ok is True
    assert "Reviewed 1 relay recoveries: recovery-timeout" in msg
    assert updates == [("recovery-timeout", "reviewed", updates[0][2])]
    assert "completed handoff" in updates[0][2]
    assert len(messages) == 3
    assert messages[1][1]["message_type"] == "relay_recovery"
    assert messages[1][1]["to_agent"] == "qwen"
    assert messages[2][0][1] == "qwen"
    assert jobs and jobs[0][0][2] == "done"


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


def test_tasker_watch_topic_creates_interest_and_scheduled_task(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    resp = client.post(
        "/api/tasker/watch-topic",
        json={
            "topic": "SAP payroll Australia",
            "schedule": "daily 06:30",
            "depth": "quick",
            "agent": "eight",
            "email": "ghost@example.com",
            "min_quality": 0.6,
            "min_novelty": 0.4,
            "min_score": 0.7,
            "max_items": 5,
        },
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["name"] == "sap_payroll_australia_watch"
    assert "interest_research_update" in data["action_data"]
    assert "'topic=SAP payroll Australia'" in data["action_data"]
    assert "email=ghost@example.com" in data["action_data"]
    assert "min_quality=0.60" in data["action_data"]
    assert "max_items=5" in data["action_data"]
    assert "historical_years=5" in data["action_data"]

    with get_conn() as conn:
        interest = conn.execute(
            "SELECT topic, category, source_agent, score, active FROM user_interests"
        ).fetchone()
        task = conn.execute(
            "SELECT name, schedule, action_type, action_data, enabled FROM scheduled_tasks"
        ).fetchone()

    assert interest["topic"] == "SAP payroll Australia"
    assert interest["category"] == "watched_research"
    assert interest["source_agent"] == "eight"
    assert interest["active"] == 1
    assert task["name"] == "sap_payroll_australia_watch"
    assert task["action_type"] == "PYTHON"
    assert task["enabled"] == 1


def test_tasker_bootstrap_seeds_successfactors_watched_topics(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp
    import fridays.scheduler as scheduler

    db_path = tmp_path / "bootstrap-watch-topics.db"
    calls = []

    def get_conn():
        return _connect(db_path)

    def fake_add_task(name, schedule, action_type, action_data, created_by="system"):
        calls.append({
            "name": name,
            "schedule": schedule,
            "action_type": action_type,
            "action_data": action_data,
            "created_by": created_by,
        })
        return len(calls)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)
    monkeypatch.setattr(scheduler, "add_task", fake_add_task)

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    resp = client.post("/api/tasker/bootstrap")

    assert resp.status_code == 200
    action_blob = "\n".join(call["action_data"] for call in calls)
    names = {call["name"] for call in calls}
    assert "sap_payroll_au_watch" in names
    assert "successfactors_employee_central_au_watch" in names
    assert "successfactors_ecp_au_watch" in names
    assert "successfactors_onboarding_2_0_au_watch" in names
    assert "successfactors_new_home_page_watch" in names
    assert "topic=SuccessFactors Employee Central Australia" in action_blob
    assert "topic=SuccessFactors Employee Central Payroll Australia" in action_blob
    assert "topic=SuccessFactors Onboarding 2.0 Australia" in action_blob
    assert "topic=SAP SuccessFactors new home page" in action_blob
    assert action_blob.count("historical_years=5") >= 5


def test_tasker_watch_topic_updates_existing_interest_and_task(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic-update.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    for schedule in ("daily 06:30", "interval 45m"):
        resp = client.post(
            "/api/tasker/watch-topic",
            json={
                "topic": "SAP payroll Australia",
                "schedule": schedule,
                "depth": "standard",
                "email": "ghost",
            },
        )
        assert resp.status_code == 200

    with get_conn() as conn:
        interests = conn.execute("SELECT * FROM user_interests").fetchall()
        tasks = conn.execute("SELECT * FROM scheduled_tasks").fetchall()

    assert len(interests) == 1
    assert len(tasks) == 1
    assert tasks[0]["schedule"] == "interval 45m"
    assert "depth=standard" in tasks[0]["action_data"]


def test_tasker_watch_topic_reuses_existing_topic_task_name(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic-existing-name.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scheduled_tasks
               (name, schedule, action_type, action_data, enabled)
               VALUES (?, ?, 'PYTHON', ?, 1)""",
            (
                "sap_payroll_au_watch",
                "daily 06:30",
                'interest_research_update topic="SAP payroll Australia" depth=standard agent=eight email=ghost',
            ),
        )
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    resp = client.post(
        "/api/tasker/watch-topic",
        json={
            "topic": "SAP payroll Australia",
            "schedule": "interval 45m",
            "depth": "quick",
            "min_score": 0.65,
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["name"] == "sap_payroll_au_watch"
    with get_conn() as conn:
        tasks = conn.execute("SELECT name, schedule, action_data FROM scheduled_tasks").fetchall()

    assert len(tasks) == 1
    assert tasks[0]["name"] == "sap_payroll_au_watch"
    assert tasks[0]["schedule"] == "interval 45m"
    assert "min_score=0.65" in tasks[0]["action_data"]
    assert "historical_years=5" in tasks[0]["action_data"]


def test_tasker_watch_topic_rejects_invalid_schedule(monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    resp = client.post(
        "/api/tasker/watch-topic",
        json={"topic": "SAP payroll Australia", "schedule": "whenever"},
    )

    assert resp.status_code == 400
    assert "Invalid schedule" in resp.get_json()["error"]


def test_tasker_watch_topic_evidence_lists_and_filters(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic-evidence.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)
    with get_conn() as conn:
        tasker_bp._ensure_watched_topic_evidence_schema(conn)
        rows = [
            (
                "sap payroll australia",
                "SAP payroll Australia",
                "url:https://www.ato.gov.au/stp",
                "https://www.ato.gov.au/stp",
                "ATO Single Touch Payroll",
                "Official ATO payroll reporting guidance.",
                0.92,
                0.95,
                0.94,
                1,
                1,
                "qualified: quality=0.92 novelty=0.95 score=0.94",
            ),
            (
                "sap payroll australia",
                "SAP payroll Australia",
                "url:http://forum.example/thread",
                "http://forum.example/thread",
                "Forum chat",
                "Weak rumour about payroll.",
                0.30,
                1.0,
                0.69,
                0,
                0,
                "filtered: quality=0.30 novelty=1.00 score=0.69",
            ),
            (
                "sap payroll australia",
                "SAP payroll Australia",
                "url:https://www.sap.com/payroll",
                "https://www.sap.com/payroll",
                "SAP Payroll overview",
                "Known SAP payroll background.",
                0.85,
                0.0,
                0.38,
                0,
                0,
                "duplicate: already known fingerprint",
            ),
        ]
        for row in rows:
            conn.execute(
                """INSERT INTO watched_topic_evidence
                   (topic_key, topic, evidence_fingerprint, source_url, title,
                    snippet, quality_score, novelty_score, combined_score,
                    qualified, notified, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    all_resp = client.get("/api/tasker/watch-topic/evidence?topic=SAP%20payroll%20Australia")
    qualified_resp = client.get("/api/tasker/watch-topic/evidence?topic=SAP%20payroll%20Australia&status=qualified")
    filtered_resp = client.get("/api/tasker/watch-topic/evidence?topic=SAP%20payroll%20Australia&status=filtered")

    assert all_resp.status_code == 200
    all_data = all_resp.get_json()
    assert all_data["ok"] is True
    assert len(all_data["evidence"]) == 3
    assert all_data["topics"][0]["topic"] == "SAP payroll Australia"
    assert all_data["topics"][0]["total"] == 3
    assert all_data["topics"][0]["qualified_count"] == 1
    assert all_data["topics"][0]["notified_count"] == 1
    assert all_data["topics"][0]["historical_count"] == 0
    assert "recency_score" in all_data["evidence"][0]
    assert "recency_label" in all_data["evidence"][0]
    assert "is_historical" in all_data["evidence"][0]

    assert qualified_resp.status_code == 200
    qualified = qualified_resp.get_json()["evidence"]
    assert len(qualified) == 1
    assert qualified[0]["qualified"] is True
    assert qualified[0]["notified"] is True
    assert "ato.gov.au" in qualified[0]["source_url"]

    assert filtered_resp.status_code == 200
    filtered = filtered_resp.get_json()["evidence"]
    assert len(filtered) == 2
    assert all(item["qualified"] is False for item in filtered)


def test_tasker_watch_topic_evidence_rejects_unknown_status(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic-evidence-status.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    resp = client.get("/api/tasker/watch-topic/evidence?status=mystery")

    assert resp.status_code == 400
    assert "status must be" in resp.get_json()["error"]


def test_tasker_watch_topic_evidence_review_actions(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic-evidence-review.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)
    with get_conn() as conn:
        tasker_bp._ensure_watched_topic_evidence_schema(conn)
        conn.execute(
            """INSERT INTO watched_topic_evidence
               (topic_key, topic, evidence_fingerprint, source_url, title,
                snippet, quality_score, novelty_score, combined_score,
                qualified, notified, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
            (
                "sap payroll australia",
                "SAP payroll Australia",
                "url:https://example.com/new",
                "https://example.com/new",
                "Potential payroll change",
                "A potentially useful item that needs human judgement.",
                0.42,
                0.91,
                0.69,
                "filtered: quality=0.42 novelty=0.91 score=0.69",
            ),
        )
        evidence_id = conn.execute("SELECT id FROM watched_topic_evidence").fetchone()["id"]
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    promote = client.patch(
        f"/api/tasker/watch-topic/evidence/{evidence_id}",
        json={"action": "promote", "note": "Useful despite low source score"},
    )
    assert promote.status_code == 200
    promoted = promote.get_json()["evidence"]
    assert promoted["qualified"] is True
    assert promoted["review_status"] == "promoted"
    assert promoted["review_note"] == "Useful despite low source score"

    notified = client.patch(
        f"/api/tasker/watch-topic/evidence/{evidence_id}",
        json={"action": "mark_notified"},
    ).get_json()["evidence"]
    assert notified["notified"] is True
    assert notified["review_status"] == "notified"

    ignored = client.patch(
        f"/api/tasker/watch-topic/evidence/{evidence_id}",
        json={"action": "ignore", "note": "Actually not relevant"},
    ).get_json()["evidence"]
    assert ignored["qualified"] is False
    assert ignored["review_status"] == "ignored"
    assert ignored["reason"] == "Actually not relevant"

    reset = client.patch(
        f"/api/tasker/watch-topic/evidence/{evidence_id}",
        json={"action": "reset"},
    ).get_json()["evidence"]
    assert reset["review_status"] == ""
    assert reset["review_note"] == ""


def test_tasker_watch_topic_evidence_review_rejects_bad_action(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic-evidence-bad-action.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    resp = client.patch("/api/tasker/watch-topic/evidence/999", json={"action": "eat"})

    assert resp.status_code == 400
    assert "action must be" in resp.get_json()["error"]


def test_tasker_run_watched_topic_now_runs_task_and_returns_evidence(tmp_path, monkeypatch):
    from flask import Flask

    import frontend.blueprints.tasker_bp as tasker_bp

    db_path = tmp_path / "watch-topic-run-now.db"
    calls = []

    def get_conn():
        return _connect(db_path)

    def fake_run_task(task_name, *, args=""):
        calls.append((task_name, args))
        with get_conn() as conn:
            tasker_bp._ensure_watched_topic_evidence_schema(conn)
            conn.execute(
                """INSERT INTO watched_topic_evidence
                   (topic_key, topic, evidence_fingerprint, source_url, title,
                    snippet, quality_score, novelty_score, combined_score,
                    qualified, notified, evidence_date, recency_score,
                    recency_label, is_historical, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, 0, ?)""",
                (
                    "sap payroll australia",
                    "SAP payroll Australia",
                    "url:https://help.sap.com/current",
                    "https://help.sap.com/current",
                    "Current SAP payroll update",
                    "Fresh watched-topic evidence.",
                    0.92,
                    0.91,
                    0.93,
                    "2026",
                    0.98,
                    "current 2026",
                    "qualified: quality=0.92 novelty=0.91 recency=0.98 score=0.93",
                ),
            )
            conn.commit()
        return True, "Research session 11 found 1 qualified new evidence item(s); email sent."

    monkeypatch.setattr(tasker_bp, "_get_conn", get_conn)
    monkeypatch.setattr("fridays.task_runner.run_task", fake_run_task)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scheduled_tasks
               (name, schedule, action_type, action_data, enabled)
               VALUES (?, 'daily 06:30', 'PYTHON', ?, 1)""",
            (
                "sap_payroll_au_watch",
                'interest_research_update topic="SAP payroll Australia" depth=standard agent=eight email=ghost',
            ),
        )
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(tasker_bp.tasker_bp)
    client = app.test_client()

    resp = client.post("/api/tasker/watch-topic/run-now", json={"topic": "SAP payroll Australia"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["name"] == "sap_payroll_au_watch"
    assert data["evidence"][0]["title"] == "Current SAP payroll update"
    assert data["evidence"][0]["recency_label"] == "current 2026"
    assert calls[0][0] == "interest_research_update"
    assert "topic=SAP payroll Australia" in calls[0][1]
    with get_conn() as conn:
        row = conn.execute("SELECT last_run FROM scheduled_tasks WHERE name='sap_payroll_au_watch'").fetchone()
    assert row["last_run"]


def test_interest_research_update_emails_only_qualified_novel_evidence(tmp_path, monkeypatch):
    import fridays.task_runner as task_runner

    db_path = tmp_path / "watched-topic.db"
    topic = "SAP payroll Australia"
    sent = []

    def get_conn():
        return _connect(db_path)

    with get_conn() as conn:
        sid = _insert_research_session(conn, topic)
        _insert_evidence(
            conn,
            sid,
            source_url="https://www.sap.com/australia/products/hcm/payroll.html",
            title="SAP Australia payroll overview",
            snippet="Known SAP payroll Australia background already reviewed by the watcher.",
            snippet_hash="known-sap",
        )
        conn.commit()

    def fake_run_research(run_topic, *, depth="standard", requesting_agent="user"):
        with get_conn() as conn:
            sid = _insert_research_session(conn, run_topic, depth=depth, summary="fresh summary")
            _insert_evidence(
                conn,
                sid,
                source_url="https://www.ato.gov.au/businesses-and-organisations/hiring-and-paying-your-workers/single-touch-payroll",
                title="Single Touch Payroll reporting",
                snippet=(
                    "The ATO explains current Single Touch Payroll reporting obligations "
                    "for Australian employers, including payroll event reporting and "
                    "employee payment information updates."
                ),
                snippet_hash="ato-stp-new",
            )
            _insert_evidence(
                conn,
                sid,
                source_url="http://randomforum.example.com/thread",
                title="Forum chat",
                snippet="Someone thinks payroll changed.",
                snippet_hash="forum-low",
            )
            _insert_evidence(
                conn,
                sid,
                source_url="https://www.sap.com/australia/products/hcm/payroll.html",
                title="SAP Australia payroll overview",
                snippet="Known SAP payroll Australia background already reviewed by the watcher.",
                snippet_hash="known-sap",
            )
            conn.commit()
        return sid, "fresh summary"

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)
    monkeypatch.setattr("fridays.research_workflow.run_research", fake_run_research)
    monkeypatch.setattr(task_runner, "_log_run", lambda *a, **k: None)
    monkeypatch.setattr(task_runner, "_email_research_update", lambda **kwargs: sent.append(kwargs) or True)

    ok, msg = task_runner.run_task(
        "interest_research_update",
        args='topic="SAP payroll Australia" depth=quick',
    )

    assert ok is True
    assert "1 qualified new evidence item" in msg
    assert len(sent) == 1
    assert len(sent[0]["evidence"]) == 1
    assert "ato.gov.au" in sent[0]["evidence"][0]["source_url"]
    assert sent[0]["evidence"][0]["combined_score"] >= 0.5
    assert sent[0]["evidence"][0]["recency_score"] >= 0.5

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT source_url, quality_score, novelty_score, combined_score,
                      qualified, notified, recency_score, recency_label,
                      is_historical, reason
               FROM watched_topic_evidence
               WHERE topic_key=?
               ORDER BY source_url""",
            ("sap payroll australia",),
        ).fetchall()

    assert len(rows) == 3
    official = next(row for row in rows if "ato.gov.au" in row["source_url"])
    forum = next(row for row in rows if "randomforum.example.com" in row["source_url"])
    duplicate = next(row for row in rows if "sap.com" in row["source_url"])
    assert official["qualified"] == 1
    assert official["notified"] == 1
    assert official["quality_score"] >= 0.45
    assert official["novelty_score"] >= 0.35
    assert official["recency_score"] >= 0.5
    assert official["is_historical"] == 0
    assert "qualified" in official["reason"]
    assert forum["qualified"] == 0
    assert forum["notified"] == 0
    assert duplicate["qualified"] == 0
    assert "duplicate" in duplicate["reason"]


def test_interest_research_update_suppresses_low_quality_new_evidence(tmp_path, monkeypatch):
    import fridays.task_runner as task_runner

    db_path = tmp_path / "watched-topic-low-quality.db"
    sent = []

    def get_conn():
        return _connect(db_path)

    def fake_run_research(topic, *, depth="standard", requesting_agent="user"):
        with get_conn() as conn:
            sid = _insert_research_session(conn, topic, depth=depth, summary="weak summary")
            _insert_evidence(
                conn,
                sid,
                source_url="http://randomforum.example.com/thread",
                title="Forum chat",
                snippet="Someone thinks payroll changed.",
                snippet_hash="forum-low-only",
            )
            conn.commit()
        return sid, "weak summary"

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)
    monkeypatch.setattr("fridays.research_workflow.run_research", fake_run_research)
    monkeypatch.setattr(task_runner, "_log_run", lambda *a, **k: None)
    monkeypatch.setattr(task_runner, "_email_research_update", lambda **kwargs: sent.append(kwargs) or True)

    ok, msg = task_runner.run_task(
        "interest_research_update",
        args='topic="SAP payroll Australia" depth=quick',
    )

    assert ok is True
    assert "none met quality/novelty thresholds" in msg
    assert sent == []
    with get_conn() as conn:
        row = conn.execute(
            """SELECT quality_score, novelty_score, combined_score, qualified, notified
               FROM watched_topic_evidence
               WHERE topic_key='sap payroll australia'""",
        ).fetchone()

    assert row is not None
    assert row["quality_score"] < 0.45
    assert row["novelty_score"] == 1.0
    assert row["combined_score"] >= 0.5
    assert row["qualified"] == 0
    assert row["notified"] == 0


def test_watched_topic_recency_filters_historical_evidence():
    from datetime import datetime

    import fridays.task_runner as task_runner

    current_year = datetime.now().year
    rows = [
        {
            "source_url": f"https://www.sap.com/australia/products/hcm/payroll-{current_year}.html",
            "title": f"SAP payroll Australia update {current_year}",
            "snippet": (
                "Current Australian payroll and SuccessFactors payroll information "
                "with practical implementation relevance for Employee Central Payroll."
            ),
            "snippet_hash": "current-sap",
        },
        {
            "source_url": "https://www.sap.com/australia/archive/payroll-2003.html",
            "title": "SAP payroll Australia archive 2003",
            "snippet": (
                "Long archived SAP payroll Australia background that may be useful "
                "as historical reference but should not trigger a current email."
            ),
            "snippet_hash": "old-sap",
        },
    ]

    assessed = task_runner._rank_watched_topic_evidence(
        "SAP payroll Australia",
        rows,
        prior_context={"fingerprints": set(), "snippets": []},
        min_quality=0.45,
        min_novelty=0.35,
        min_score=0.50,
        historical_years=5,
    )

    current = next(item for item in assessed if item["snippet_hash"] == "current-sap")
    old = next(item for item in assessed if item["snippet_hash"] == "old-sap")
    assert current["qualified"] is True
    assert current["is_historical"] is False
    assert str(current_year) in current["recency_label"]
    assert old["qualified"] is False
    assert old["is_historical"] is True
    assert "2003" in old["recency_label"]
    assert "historical reference" in old["reason"]


def test_email_research_update_includes_interactive_date_and_historical_sections(monkeypatch):
    import fridays.task_runner as task_runner

    sent = []

    def fake_send_reply(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setenv("SWARM_UI_URL", "http://studio.local/ui")
    monkeypatch.setattr("lib.email.email_handler.send_reply", fake_send_reply)

    ok = task_runner._email_research_update(
        topic="SAP payroll Australia",
        session_id=77,
        summary="summary",
        recipient="ghost",
        agent="eight",
        evidence=[{
            "title": "SAP SuccessFactors Employee Central Payroll Australia 2026",
            "source_url": "https://help.sap.com/docs/successfactors/ecp",
            "snippet": "Current guidance for Employee Central Payroll Australia.",
            "combined_score": 0.94,
            "quality_score": 0.93,
            "novelty_score": 0.95,
            "recency_score": 0.98,
            "recency_label": "current 2026",
        }],
        historical_refs=[{
            "title": "SAP payroll Australia archive 2003",
            "source_url": "https://www.sap.com/archive/2003",
            "recency_label": "long-ago 2003",
        }],
    )

    assert ok is True
    assert len(sent) == 1
    assert sent[0]["subject"] == "[Swarm Research] Current update: SAP payroll Australia"
    body = sent[0]["body"]
    assert "Review in Studio: http://studio.local/ui?view=tasker&watch_topic=SAP%20payroll%20Australia" in body
    assert "promote, ignore, or mark findings as emailed" in body
    assert "Current and relevant evidence:" in body
    assert "Employee Central Payroll Australia" in body
    assert "recency=0.98" in body
    assert "date=current 2026" in body
    assert "Historical reference / fun fact from long ago:" in body
    assert "long-ago 2003" in body
