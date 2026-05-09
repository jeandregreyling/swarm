"""Session 30.1 — Projects (Agile/Waterfall/Prince2) persistence tests.

Projects are first-class: proposals, plan steps, test cases and test runs
all hang off a project. Seven is the default owner. Every mutation emits a
spine TICKET event sourced 'projects' (auto-feeds Vortex).

TARGETED test file (Session 30 QA directive).
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    from utils.db import _connection as conn_mod
    db_path = tmp_path / "projects.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setattr(conn_mod, "DB_PATH", str(db_path), raising=False)
    import core.knowledge.projects as pj
    import core.knowledge.test_runs as tr
    monkeypatch.setattr(pj, "_SCHEMA_READY", False, raising=False)
    monkeypatch.setattr(tr, "_SCHEMA_READY", False, raising=False)
    yield db_path


# ── create_project ──────────────────────────────────────────────────────────

def test_create_project_default_owner_is_seven(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("QA Spine", description="Session 30 QA")
    assert pid and pid.startswith("P-")
    p = pj.get_project(pid)
    assert p["project"]["owner"] == "seven"
    assert p["project"]["methodology"] == "mixed"
    assert p["project"]["status"] == "active"


def test_create_project_rejects_bad_methodology(isolated_db):
    from core.knowledge import projects as pj
    with pytest.raises(ValueError):
        pj.create_project("Bad", methodology="scrumish")


def test_create_project_accepts_all_methodologies(isolated_db):
    from core.knowledge import projects as pj
    for m in pj.METHODOLOGIES:
        pid = pj.create_project(f"Proj {m}", methodology=m)
        assert pid
        assert pj.get_project(pid)["project"]["methodology"] == m


def test_create_project_requires_name(isolated_db):
    from core.knowledge import projects as pj
    with pytest.raises(ValueError):
        pj.create_project("   ")


# ── list_projects ───────────────────────────────────────────────────────────

def test_list_projects_returns_aggregates(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("Agg test", methodology="agile")
    pj.add_step(pid, "step 1")
    pj.add_step(pid, "step 2")
    pj.add_test_case(pid, "case 1")
    pj.add_blackboard_note(pid, "Visible handoff", kind="handoff")
    items = pj.list_projects()
    row = [x for x in items if x["project_id"] == pid][0]
    assert row["step_count"] == 2
    assert row["case_count"] == 1
    assert row["blackboard_count"] == 1
    assert row["steps_done"] == 0


def test_list_projects_status_filter(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("archive me")
    pj.update_project(pid, status="archived")
    assert not any(x["project_id"] == pid for x in pj.list_projects(status="active"))
    assert any(x["project_id"] == pid for x in pj.list_projects(status="archived"))


# ── steps ───────────────────────────────────────────────────────────────────

def test_add_step_auto_increments_order(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("plan test")
    s1 = pj.add_step(pid, "first")
    s2 = pj.add_step(pid, "second")
    steps = pj.list_steps(pid)
    assert len(steps) == 2
    order_map = {s["step_id"]: s["order_idx"] for s in steps}
    assert order_map[s1] < order_map[s2]


def test_update_step_status_validates(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("plan test")
    sid = pj.add_step(pid, "first")
    assert pj.update_step_status(sid, "doing")
    with pytest.raises(ValueError):
        pj.update_step_status(sid, "maybe")


def test_steps_default_owner_seven(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("owner test")
    sid = pj.add_step(pid, "first")
    step = [s for s in pj.list_steps(pid) if s["step_id"] == sid][0]
    assert step["owner"] == "seven"


def test_list_projects_counts_only_done_steps(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("progress test")
    s1 = pj.add_step(pid, "a")
    pj.add_step(pid, "b")
    pj.update_step_status(s1, "done")
    row = [x for x in pj.list_projects() if x["project_id"] == pid][0]
    assert row["step_count"] == 2
    assert row["steps_done"] == 1


# ── blackboard ──────────────────────────────────────────────────────────────

def test_blackboard_notes_are_project_scoped_and_statused(isolated_db):
    from core.knowledge import projects as pj

    pid = pj.create_project("blackboard project")
    note_id = pj.add_blackboard_note(
        pid,
        "Duck should verify the next recovery sweep before it runs active agents.",
        author="duck",
        kind="risk",
    )

    assert note_id and note_id.startswith("B-")
    notes = pj.list_blackboard_notes(pid)
    assert len(notes) == 1
    assert notes[0]["author"] == "duck"
    assert notes[0]["kind"] == "risk"
    assert "verify the next recovery sweep" in notes[0]["content"]

    detail = pj.get_project(pid)
    assert detail["blackboard_notes"][0]["note_id"] == note_id

    assert pj.update_blackboard_note_status(note_id, "resolved") is True
    assert pj.list_blackboard_notes(pid) == []
    all_notes = pj.list_blackboard_notes(pid, status=None)
    assert all_notes[0]["status"] == "resolved"


def test_blackboard_rejects_unknown_kind(isolated_db):
    from core.knowledge import projects as pj

    pid = pj.create_project("blackboard validation")
    with pytest.raises(ValueError):
        pj.add_blackboard_note(pid, "bad kind", kind="vibes")


def test_blackboard_api_create_list_and_resolve(isolated_db):
    from flask import Flask
    from core.knowledge import projects as pj
    from frontend.blueprints.knowledge_bp import knowledge_bp

    pid = pj.create_project("blackboard api")
    app = Flask(__name__)
    app.register_blueprint(knowledge_bp)
    client = app.test_client()

    created = client.post(
        f"/api/knowledge/projects/{pid}/blackboard",
        json={"kind": "handoff", "author": "duck", "content": "Next agent should run the focused relay tests."},
    )
    assert created.status_code == 200
    note_id = created.get_json()["note_id"]

    listed = client.get(f"/api/knowledge/projects/{pid}/blackboard")
    data = listed.get_json()
    assert listed.status_code == 200
    assert data["items"][0]["note_id"] == note_id
    assert data["items"][0]["kind"] == "handoff"

    resolved = client.patch(
        f"/api/knowledge/blackboard/{note_id}",
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert client.get(f"/api/knowledge/projects/{pid}/blackboard").get_json()["items"] == []
    all_notes = client.get(f"/api/knowledge/projects/{pid}/blackboard?status=all").get_json()["items"]
    assert all_notes[0]["status"] == "resolved"


def test_project_context_preview_api_uses_project_pack(isolated_db):
    from flask import Flask
    from core.knowledge import projects as pj
    from frontend.blueprints.knowledge_bp import knowledge_bp

    pid = pj.create_project("context preview", description="Preview what a local agent will see.")
    pj.add_step(pid, "wire preview drawer")
    pj.add_test_case(pid, "preview js syntax", script_id="node --check frontend/static/js/views/projects.js")
    pj.add_blackboard_note(pid, "The next agent should verify the preview endpoint.", author="codex", kind="handoff")

    app = Flask(__name__)
    app.register_blueprint(knowledge_bp)
    client = app.test_client()

    resp = client.get(f"/api/knowledge/projects/{pid}/context-preview")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert "Studio project context" in data["context"]
    assert "context preview" in data["context"]
    assert "wire preview drawer" in data["context"]
    assert "preview js syntax" in data["context"]
    assert "The next agent should verify the preview endpoint" in data["context"]


def test_project_context_resolves_from_steps_tests_and_blackboard(isolated_db):
    from core.knowledge import context_packs
    from core.knowledge import projects as pj

    pid = pj.create_project("Integration Improvement Audit 2026-04-28")
    pj.add_step(pid, "Add SAP payroll Australia watcher")
    pj.add_test_case(pid, "Tasker relay recovery sweep dry-run reports open cards")
    pj.add_blackboard_note(
        pid,
        "relay_recovery_sweep is the active handoff path for stalled agents.",
        author="codex",
        kind="handoff",
    )

    assert context_packs.resolve_project_context_id("Any SAP payroll Australia updates?") == pid
    assert context_packs.resolve_project_context_id("Check relay_recovery_sweep before the next agent run") == pid


def test_project_context_resolves_from_task_interest_and_research_triggers(isolated_db):
    from utils.db._connection import get_connection
    from core.knowledge import context_packs
    from core.knowledge import projects as pj

    pid = pj.create_project("Watcher and Research Integration")
    pj.add_step(pid, "Harden interest_research_update scheduler workflow")
    pj.add_step(pid, "Deep research synthesis workflow for agent handoffs")

    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                schedule TEXT,
                action_type TEXT,
                action_data TEXT,
                enabled INTEGER DEFAULT 1
            );
            CREATE TABLE user_interests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT DEFAULT 'ghost',
                topic TEXT,
                category TEXT,
                source_agent TEXT DEFAULT '',
                score REAL DEFAULT 10,
                active INTEGER DEFAULT 1,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE research_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                summary TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            """INSERT INTO scheduled_tasks (name, schedule, action_type, action_data, enabled)
               VALUES ('sap_payroll_au_watch', 'daily 06:30', 'PYTHON',
                       'interest_research_update topic="SAP payroll Australia"', 1)"""
        )
        conn.execute(
            """INSERT INTO user_interests (topic, category, source_agent, score, active)
               VALUES ('Project Helios packaging', 'research', 'scholar', 15, 1)"""
        )
        conn.execute(
            """INSERT INTO research_sessions (topic, summary)
               VALUES ('Project Helios packaging', 'deep research synthesis workflow for agent handoffs')"""
        )
        conn.commit()
    finally:
        conn.close()

    assert context_packs.resolve_project_context_id("sap_payroll_au_watch needs checking") == pid
    assert context_packs.resolve_project_context_id("Continue Project Helios research") == pid


# ── test cases ──────────────────────────────────────────────────────────────

def test_add_case_without_step(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("cases")
    cid = pj.add_test_case(pid, "smoke case", script_id="pytest:spine")
    cases = pj.list_test_cases(pid)
    assert len(cases) == 1
    assert cases[0]["case_id"] == cid
    assert cases[0]["owner"] == "seven"


def test_add_case_with_step_filter(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("cases")
    sid = pj.add_step(pid, "step A")
    c1 = pj.add_test_case(pid, "A-case", step_id=sid)
    pj.add_test_case(pid, "floating-case")
    filtered = pj.list_test_cases(pid, step_id=sid)
    assert [c["case_id"] for c in filtered] == [c1]


# ── proposal linking ────────────────────────────────────────────────────────

def test_link_proposal_dedupes(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("linked")
    assert pj.link_proposal(pid, "1306")
    assert pj.link_proposal(pid, "1306")  # idempotent (no row created)
    props = pj.list_proposals_for_project(pid)
    assert [p["proposal_id"] for p in props] == ["1306"]


# ── test_runs integration ───────────────────────────────────────────────────

def test_test_run_tagged_with_project_is_filterable(isolated_db):
    from core.knowledge import projects as pj
    from core.knowledge import test_runs as tr
    pid = pj.create_project("run tag test")
    sid = pj.add_step(pid, "step")
    cid = pj.add_test_case(pid, "case", step_id=sid)
    rid = tr.start_run("pytest:spine", change_id="CR-1", project_id=pid, step_id=sid, case_id=cid)
    assert rid
    runs = tr.list_runs(project_id=pid)
    assert any(r["run_id"] == rid for r in runs)
    runs_step = tr.list_runs(step_id=sid)
    assert any(r["run_id"] == rid for r in runs_step)


def test_test_run_without_project_still_works(isolated_db):
    from core.knowledge import test_runs as tr
    rid = tr.start_run("pytest:spine", change_id="CR-legacy")
    assert rid
    runs = tr.list_runs()
    assert any(r["run_id"] == rid for r in runs)


# ── get_project aggregate ───────────────────────────────────────────────────

def test_get_project_returns_full_tree(isolated_db):
    from core.knowledge import projects as pj
    pid = pj.create_project("full tree", methodology="prince2")
    sid = pj.add_step(pid, "plan step")
    pj.add_test_case(pid, "plan case", step_id=sid)
    pj.link_proposal(pid, "1306")
    p = pj.get_project(pid)
    assert p["project"]["project_id"] == pid
    assert len(p["steps"]) == 1
    assert len(p["test_cases"]) == 1
    assert len(p["proposals"]) == 1
