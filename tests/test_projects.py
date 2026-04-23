"""Session 30.1 — Projects (Agile/Waterfall/Prince2) persistence tests.

Projects are first-class: proposals, plan steps, test cases and test runs
all hang off a project. Seven is the default owner. Every mutation emits a
spine TICKET event sourced 'projects' (auto-feeds Vortex).

TARGETED test file (Session 30 QA directive).
"""
from __future__ import annotations

import pytest


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
    items = pj.list_projects()
    row = [x for x in items if x["project_id"] == pid][0]
    assert row["step_count"] == 2
    assert row["case_count"] == 1
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
