"""Full read/write Studio task access for APEX and Shakira across all owners (take ownership, update, add notes)."""
from __future__ import annotations

from contextlib import closing

import pytest

from core import agent_identity, apex_alm, hb_homework, hb_tasks


@pytest.fixture
def isolated_studio(tmp_path, monkeypatch):
    from utils.db import _connection as conn_mod
    import core.knowledge.projects as projects
    import core.knowledge.test_runs as test_runs
    db_path = tmp_path / "rw_studio.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setattr(conn_mod, "DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(projects, "_SCHEMA_READY", False, raising=False)
    monkeypatch.setattr(test_runs, "_SCHEMA_READY", False, raising=False)
    return projects, conn_mod


def test_apex_can_read_claim_note_and_update_any_owner_step(isolated_studio, monkeypatch):
    projects, conn_mod = isolated_studio
    pid = projects.create_project("Roadmap", description="Master roadmap")
    jd_step = projects.add_step(pid, "Online providers: Gemini, Codex, others", description="Owner item.", owner="jd")
    jd_case = projects.add_test_case(pid, "Verify provider", step_id=jd_step)

    info = apex_alm.read_step(jd_step)
    assert info["status"] == "found" and info["owner"] == "jd" and info["writable"] is True and info["read_only"] is False

    res = apex_alm.run_recorded_tests(
        {"tests": ["tests/test_x.py"], "case_id": jd_case},
        lambda _a: {"status": "passed", "exit_code": 0, "summary": "1 passed", "verdict": "PASS: 1 passed"},
        validate=lambda a: (a["tests"], None),
    )
    assert res["alm_run_status"] == "pass"

    with closing(conn_mod.get_connection()) as conn, conn:
        hb_tasks.ensure_schema(conn)
        conn.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES (1,'user','apex','help','chat')").lastrowid
        task = hb_tasks.bind(conn, 1, mid, title="Work", objective="Help JD", project_id=pid, step_id=jd_step)
        assert task["step_id"] == jd_step

    tok = agent_identity.CURRENT.set({"principal": "apex", "conversation_id": 1, "task_id": task["task_id"]})
    try:
        st = hb_tasks.call("studio_status", {"status": "doing", "step_id": jd_step, "owner": "apex", "note": "APEX taking ownership"})
        assert st["step_id"] == jd_step and st["owner"] == "apex" and st["status"] == "doing"
        nt = hb_tasks.call("studio_note", {"content": "Added technical context", "step_id": jd_step})
        assert nt["step_id"] == jd_step and nt["project_id"] == pid
    finally:
        agent_identity.CURRENT.reset(tok)

    updated = projects.get_step(jd_step)
    assert updated["owner"] == "apex" and updated["status"] == "doing"
    assert "APEX taking ownership" in (updated["description"] or "")


def test_shakira_can_update_note_and_claim_any_step(isolated_studio):
    projects, conn_mod = isolated_studio
    pid = projects.create_project("Roadmap", description="Master roadmap")
    jd_step = projects.add_step(pid, "Rig benchmark", description="Run hw_bench.py.", owner="jd")
    with closing(conn_mod.get_connection()) as conn, conn:
        out = hb_homework.update_step(conn, jd_step, owner="shakira", status="partial", note="BA reviewed scope with JD")
    assert out["ok"] is True and out["owner"] == "shakira" and out["status"] == "partial"
    step = projects.get_step(jd_step)
    assert step["owner"] == "shakira" and step["status"] == "partial"
    assert "BA reviewed scope with JD" in (step["description"] or "")
