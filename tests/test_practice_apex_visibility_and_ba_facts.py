"""Full read-only Studio visibility for APEX, tighter doer_ok against planning-only promises, and Shakira BA step lookups."""
from __future__ import annotations

from contextlib import closing

import pytest

from core import apex_alm, apex_tools, hb_homework, hb_tasks


@pytest.fixture
def isolated_studio(tmp_path, monkeypatch):
    from utils.db import _connection as conn_mod
    import core.knowledge.projects as projects
    import core.knowledge.test_runs as test_runs
    db_path = tmp_path / "studio_vis.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setattr(conn_mod, "DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(projects, "_SCHEMA_READY", False, raising=False)
    monkeypatch.setattr(test_runs, "_SCHEMA_READY", False, raising=False)
    return projects, conn_mod


def test_alm_read_step_shows_non_apex_steps_read_only(isolated_studio):
    projects, _ = isolated_studio
    pid = projects.create_project("Test Plan", description="Visibility check")
    sid = projects.add_step(pid, "Online providers: Gemini, Codex, others", description="Owner-invoked provider roadmap.", owner="jd")
    res = apex_alm.read_step(sid)
    assert res["status"] == "found"
    assert res["step_id"] == sid
    assert res["title"] == "Online providers: Gemini, Codex, others"
    assert res["owner"] == "jd"
    assert res["assigned_to_apex"] is False
    assert res["read_only"] is False
    assert res["writable"] is True
    assert "full read/write access" in res["checklist_note"]


def test_doer_ok_still_rejects_next_step_promise_after_studio_task_only():
    receipts = [
        {"tool": "studio_task", "status": "succeeded", "id": "r1", "output": '{"state": "planned", "deduplicated": true}'},
    ]
    assert not apex_tools.doer_ok("I have created a task. The next step is to create a task for the rig benchmark.", receipts)
    assert not apex_tools.doer_ok("I will now create the next task.", receipts)
    real_receipts = [{"tool": "propose_patch", "status": "succeeded", "id": "r2"}]
    assert apex_tools.doer_ok("Patched core/x.py (receipt r2). The next step is to review it.", real_receipts)


def test_shakira_facts_resolves_referenced_studio_steps(isolated_studio):
    projects, conn_mod = isolated_studio
    pid = projects.create_project("Roadmap", description="Master roadmap")
    sid = projects.add_step(pid, "Rig benchmark and overclock ladder", description="Run hw_bench.py with sudo.", owner="jd")
    with closing(conn_mod.get_connection()) as conn:
        hb_tasks.ensure_schema(conn)
        gathered = hb_homework.facts(conn, {"task_id": "T-TEST000001", "step_id": None, "title": f"Roadmap item {sid}", "objective": f"Check {sid} in the roadmap"})
    steps = gathered.get("studio_steps") or []
    assert len(steps) == 1
    assert steps[0]["step_id"] == sid
    assert steps[0]["title"] == "Rig benchmark and overclock ladder"
    assert steps[0]["owner"] == "jd"
