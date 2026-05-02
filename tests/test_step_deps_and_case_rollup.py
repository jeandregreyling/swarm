"""Tests for step dependencies + test-run case rollup.

Covers:
  * S-98FA0FAEFE — project_step_deps table + add/remove/list helpers + API
  * S-D12CB0E012 — test-case status rolled up from finish_run outcome
  * S-8BF99BC49E — test_runs.command captured by start_run (existing surface)
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm_memory.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setenv("SWARM_ROOT", str(ROOT))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from utils.db import _connection
    importlib.reload(_connection)
    from utils.db import _schema
    importlib.reload(_schema)
    _schema.initialise_database()
    from core.knowledge import projects as kc
    importlib.reload(kc)
    from core.knowledge import test_runs as tr
    importlib.reload(tr)
    from frontend.blueprints import knowledge_bp as kbp
    importlib.reload(kbp)
    app = Flask(__name__)
    app.register_blueprint(kbp.knowledge_bp)
    app.config["TESTING"] = True
    return app.test_client(), kc, tr


# ── S-98FA0FAEFE: step dependencies ─────────────────────────────────────────

def _new_project_with_steps(client, n=3):
    pid = client.post(
        "/api/knowledge/projects", json={"name": "DepProj"}
    ).get_json()["project_id"]
    sids = []
    for i in range(n):
        r = client.post(
            f"/api/knowledge/projects/{pid}/steps",
            json={"title": f"step-{i}"},
        )
        sids.append(r.get_json()["step_id"])
    return pid, sids


def test_add_and_list_step_dependency(env):
    client, kc, tr = env
    _, (s0, s1, s2) = _new_project_with_steps(client, 3)
    assert kc.add_step_dependency(s2, s0) is True
    assert kc.add_step_dependency(s2, s1) is True
    deps = kc.list_step_dependencies(s2)
    assert {d["step_id"] for d in deps} == {s0, s1}
    blockers_of_s0 = kc.list_step_blockers(s0)
    assert {b["step_id"] for b in blockers_of_s0} == {s2}


def test_add_dep_idempotent(env):
    client, kc, tr = env
    _, (s0, s1, _) = _new_project_with_steps(client, 3)
    kc.add_step_dependency(s1, s0)
    kc.add_step_dependency(s1, s0)  # second call should be a no-op, not error
    assert len(kc.list_step_dependencies(s1)) == 1


def test_self_dep_rejected(env):
    client, kc, tr = env
    _, (s0, _, _) = _new_project_with_steps(client, 3)
    with pytest.raises(ValueError, match="cannot depend on itself"):
        kc.add_step_dependency(s0, s0)


def test_simple_cycle_rejected(env):
    client, kc, tr = env
    _, (s0, s1, _) = _new_project_with_steps(client, 3)
    kc.add_step_dependency(s1, s0)
    with pytest.raises(ValueError, match="cycle"):
        kc.add_step_dependency(s0, s1)


def test_unknown_step_rejected(env):
    client, kc, tr = env
    _, (s0, _, _) = _new_project_with_steps(client, 3)
    with pytest.raises(ValueError, match="unknown step_id"):
        kc.add_step_dependency(s0, "S-DOESNOTEXIST")


def test_remove_step_dependency(env):
    client, kc, tr = env
    _, (s0, s1, _) = _new_project_with_steps(client, 3)
    kc.add_step_dependency(s1, s0)
    assert kc.remove_step_dependency(s1, s0) is True
    assert kc.list_step_dependencies(s1) == []
    # removing a missing edge returns False
    assert kc.remove_step_dependency(s1, s0) is False


def test_dependencies_api(env):
    client, kc, tr = env
    _, (s0, s1, s2) = _new_project_with_steps(client, 3)
    r = client.post(
        f"/api/knowledge/steps/{s2}/dependencies",
        json={"depends_on": s0},
    )
    assert r.status_code == 200
    listing = client.get(f"/api/knowledge/steps/{s2}/dependencies").get_json()
    assert listing["ok"] is True
    assert {d["step_id"] for d in listing["depends_on"]} == {s0}
    # remove via DELETE
    r = client.delete(f"/api/knowledge/steps/{s2}/dependencies/{s0}")
    assert r.status_code == 200
    after = client.get(f"/api/knowledge/steps/{s2}/dependencies").get_json()
    assert after["depends_on"] == []


def test_dependencies_api_400_when_missing_body(env):
    client, kc, tr = env
    _, (s0, _, _) = _new_project_with_steps(client, 3)
    r = client.post(f"/api/knowledge/steps/{s0}/dependencies", json={})
    assert r.status_code == 400


# ── S-D12CB0E012: test-case rollup from finish_run ──────────────────────────

def _new_case(client, kc, project_id, step_id, title="case"):
    cid = kc.add_test_case(project_id, title, step_id=step_id)
    return cid


def test_finish_pass_rolls_case_to_passed(env):
    client, kc, tr = env
    pid, (s0, _, _) = _new_project_with_steps(client, 3)
    cid = _new_case(client, kc, pid, s0)
    run = tr.start_run("script.sh", project_id=pid, step_id=s0, case_id=cid,
                       command="echo run")
    assert run
    assert tr.finish_run(run, status=tr.STATUS_PASS, exit_code=0) is True
    case = kc.get_test_case(cid)
    assert case["status"] == "passed"


def test_finish_fail_rolls_case_to_failed(env):
    client, kc, tr = env
    pid, (s0, _, _) = _new_project_with_steps(client, 3)
    cid = _new_case(client, kc, pid, s0)
    run = tr.start_run("s.sh", project_id=pid, step_id=s0, case_id=cid)
    tr.finish_run(run, status=tr.STATUS_FAIL, exit_code=1)
    assert kc.get_test_case(cid)["status"] == "failed"


def test_error_run_also_marks_case_failed(env):
    client, kc, tr = env
    pid, (s0, _, _) = _new_project_with_steps(client, 3)
    cid = _new_case(client, kc, pid, s0)
    run = tr.start_run("s.sh", project_id=pid, step_id=s0, case_id=cid)
    tr.finish_run(run, status=tr.STATUS_ERROR, exit_code=2)
    assert kc.get_test_case(cid)["status"] == "failed"


def test_aborted_run_blocks_case(env):
    client, kc, tr = env
    pid, (s0, _, _) = _new_project_with_steps(client, 3)
    cid = _new_case(client, kc, pid, s0)
    run = tr.start_run("s.sh", project_id=pid, step_id=s0, case_id=cid)
    tr.abort_run(run, reason="user cancel")
    assert kc.get_test_case(cid)["status"] == "blocked"


def test_obsolete_case_not_overwritten(env):
    client, kc, tr = env
    pid, (s0, _, _) = _new_project_with_steps(client, 3)
    cid = _new_case(client, kc, pid, s0)
    kc.update_case_status(cid, "obsolete")
    run = tr.start_run("s.sh", project_id=pid, step_id=s0, case_id=cid)
    tr.finish_run(run, status=tr.STATUS_PASS, exit_code=0)
    # rollup must not resurrect an obsolete case
    assert kc.get_test_case(cid)["status"] == "obsolete"


def test_run_without_case_does_not_crash(env):
    client, kc, tr = env
    pid, (s0, _, _) = _new_project_with_steps(client, 3)
    run = tr.start_run("s.sh", project_id=pid, step_id=s0)
    assert tr.finish_run(run, status=tr.STATUS_PASS, exit_code=0) is True


# ── S-8BF99BC49E: command captured ──────────────────────────────────────────

def test_run_command_captured_by_start_run(env):
    client, kc, tr = env
    pid, (s0, _, _) = _new_project_with_steps(client, 3)
    run = tr.start_run("script.sh", project_id=pid, step_id=s0,
                       command="bash run.sh --flag value")
    rec = tr.get_run(run)
    assert rec is not None
    assert rec["command"] == "bash run.sh --flag value"
