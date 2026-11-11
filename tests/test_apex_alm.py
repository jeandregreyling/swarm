import pytest

from core import apex_alm


@pytest.fixture
def alm(tmp_path, monkeypatch):
    from utils.db import _connection as conn_mod
    import core.knowledge.projects as projects
    import core.knowledge.test_runs as test_runs
    db_path = tmp_path / "alm.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setattr(conn_mod, "DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(projects, "_SCHEMA_READY", False, raising=False)
    monkeypatch.setattr(test_runs, "_SCHEMA_READY", False, raising=False)
    project = projects.create_project("APEX training")
    step = projects.add_step(project, "Find and run tests", description="Use tests/", owner="apex")
    case = projects.add_test_case(project, "Run evidence tests", step_id=step)
    other = projects.add_step(project, "Seven only", owner="seven")
    other_case = projects.add_test_case(project, "Not APEX", step_id=other)
    return {"projects": projects, "runs": test_runs, "project": project, "step": step,
            "case": case, "other": other, "other_case": other_case}


def passing(args):
    return {"status": "passed", "exit_code": 0, "summary": "2 passed", "output_tail": "..",
            "tests": args["tests"]}


def accept(args):
    return args["tests"], args.get("keyword")


def test_read_step_returns_apex_assignment_with_cases(alm):
    result = apex_alm.read_step(alm["step"])
    assert result["status"] == "found" and result["title"] == "Find and run tests"
    assert [case["case_id"] for case in result["test_cases"]] == [alm["case"]]


def test_read_step_hides_steps_not_assigned_to_apex(alm):
    result = apex_alm.read_step(alm["other"])
    assert result["status"] == "not_assigned" and "title" not in result
    assert apex_alm.read_step("S-0000000000")["status"] == "not_found"


@pytest.mark.parametrize("bad", ["", "S-1", "s-0123456789", "../x", 5, None])
def test_read_step_rejects_malformed_ids(alm, bad):
    with pytest.raises(ValueError):
        apex_alm.read_step(bad)


def test_recorded_run_saves_real_outcome_on_the_case(alm):
    result = apex_alm.run_recorded_tests(
        {"tests": ["tests/test_x.py"], "keyword": "truncated", "case_id": alm["case"]},
        passing, validate=accept)
    run = alm["runs"].get_run(result["alm_run_id"])
    assert list(result)[:3] == ["verdict", "alm_run_id", "alm_run_status"]
    assert run["status"] == "pass" and run["triggered_by"] == "apex"
    assert run["case_id"] == alm["case"] and run["step_id"] == alm["step"]
    assert "2 passed" in run["stdout_tail"] and "-k 'truncated'" in run["command"]
    assert alm["projects"].get_test_case(alm["case"])["status"] == "passed"
    step = apex_alm.read_step(alm["step"])
    assert "recent_runs" not in step and "not results of this turn" in step["earlier_runs_note"]
    assert [run["run_id"] for run in step["earlier_runs"]] == [result["alm_run_id"]]


def test_failed_and_busy_runs_are_not_recorded_as_passes(alm):
    failed = apex_alm.run_recorded_tests(
        {"tests": ["tests/test_x.py"], "case_id": alm["case"]},
        lambda args: {"status": "failed", "exit_code": 1, "summary": "1 failed"}, validate=accept)
    assert alm["runs"].get_run(failed["alm_run_id"])["status"] == "fail"
    busy = apex_alm.run_recorded_tests(
        {"tests": ["tests/test_x.py"], "case_id": alm["case"]},
        lambda args: {"status": "busy", "detail": "no tests started"}, validate=accept)
    assert alm["runs"].get_run(busy["alm_run_id"])["status"] == "aborted"


def test_case_letter_keyword_with_its_own_case_id_runs_the_file_for_that_case(alm):
    case_a = alm["projects"].add_test_case(alm["project"], "A: evidence file passes", step_id=alm["step"])
    ran = []
    result = apex_alm.run_recorded_tests(
        {"tests": ["tests/test_x.py"], "keyword": "A", "case_id": case_a},
        lambda args: ran.append(args) or passing(args), validate=accept)
    assert ran == [{"tests": ["tests/test_x.py"]}]
    assert "keyword 'A' was dropped" in result["note"] and case_a in result["note"]
    assert "-k" not in alm["runs"].get_run(result["alm_run_id"])["command"]


def test_case_id_cannot_accidentally_filter_every_pytest_out(alm):
    ran=[]
    result=apex_alm.run_recorded_tests({'tests':['tests/test_x.py'],'keyword':alm['case'],'case_id':alm['case']},
        lambda args:ran.append(args) or passing(args),validate=accept)
    assert ran==[{'tests':['tests/test_x.py']}]
    assert 'case_id already selects' in result['note']
    assert '-k' not in alm['runs'].get_run(result['alm_run_id'])['command']


def test_different_case_id_keyword_is_rejected_before_starting_pytest(alm):
    with pytest.raises(ValueError,match='another ALM case ID'):
        apex_alm.run_recorded_tests({'tests':['tests/test_x.py'],'keyword':alm['other_case'],'case_id':alm['case']},
            lambda _:pytest.fail('Invalid case filter must not start pytest'),validate=accept)


def test_case_letter_keyword_for_a_different_case_is_still_validated(alm):
    case_a = alm["projects"].add_test_case(alm["project"], "A: evidence file passes", step_id=alm["step"])
    seen = []

    def reject_short(args):
        seen.append(args)
        raise ValueError("keyword 'B' is not a test name")
    with pytest.raises(ValueError, match="not a test name"):
        apex_alm.run_recorded_tests({"tests": ["tests/test_x.py"], "keyword": "B", "case_id": case_a},
                                    passing, validate=reject_short)
    assert seen == [{"tests": ["tests/test_x.py"], "keyword": "B"}]


def test_case_title_used_as_keyword_is_refused_with_the_fix_and_creates_no_run(alm):
    case_a = alm["projects"].add_test_case(alm["project"], "A: Execute correct boundary test", step_id=alm["step"])
    with pytest.raises(ValueError) as error:
        apex_alm.run_recorded_tests({"tests": ["tests/test_x.py"], "keyword": "A: execute correct boundary test",
                                     "case_id": case_a}, passing, validate=lambda args: pytest.fail("validated"))
    assert f"is the title of case {case_a}, not a test name" in str(error.value)
    assert "function name copied from your grep_repo receipt" in str(error.value) and "NOT RUN" in str(error.value)
    assert alm["runs"].list_runs(case_id=case_a) == []


def test_cases_outside_apex_steps_and_bad_args_create_no_run(alm):
    calls = []
    with pytest.raises(PermissionError, match="NOT RUN: no pytest started"):
        apex_alm.run_recorded_tests({"tests": ["tests/test_x.py"], "case_id": alm["other_case"]},
                                    calls.append, validate=accept)
    with pytest.raises(ValueError, match="NOT RUN: no pytest started"):
        apex_alm.run_recorded_tests({"tests": ["tests/test_x.py"], "case_id": "C-1"},
                                    calls.append, validate=accept)

    def reject(args):
        raise PermissionError("not tracked")
    with pytest.raises(PermissionError):
        apex_alm.run_recorded_tests({"tests": ["/etc/passwd"], "case_id": alm["case"]},
                                    calls.append, validate=reject)
    assert calls == []
    assert alm["projects"].get_step(alm["step"])["test_runs"] == []


def test_dispatcher_routes_alm_reads_and_recorded_runs():
    import json
    from core.apex_tools import run_apex_tools
    replies = iter([
        json.dumps({"tool_calls": [
            {"name": "alm_step_get", "arguments": {"step_id": "S-0123456789"}},
            {"name": "run_tests", "arguments": {"tests": ["tests/test_x.py"], "case_id": "C-0123456789"}}],
            "answer": ""}),
        json.dumps({"tool_calls": [], "answer": "done"}),
    ])
    seen = []

    def studio(name, args):
        seen.append((name, args))
        return {"status": "found"}

    def tests(args):
        seen.append(("run_tests", args))
        return {"status": "passed", "alm_run_id": "R1"}
    _, _, receipts = run_apex_tools(lambda *_: (next(replies), 1),
                                    [{"role": "user", "content": "Work S-0123456789"}],
                                    lambda: True, lambda _: None,
                                    studio_handler=studio, test_handler=tests)
    assert [receipt["status"] for receipt in receipts] == ["succeeded", "succeeded"]
    assert seen == [("alm_step_get", {"step_id": "S-0123456789"}),
                    ("run_tests", {"tests": ["tests/test_x.py"], "case_id": "C-0123456789"})]
    denied = iter([replies_first := json.dumps({"tool_calls": [
        {"name": "alm_step_get", "arguments": {"step_id": "S-0123456789"}}], "answer": ""}),
        json.dumps({"tool_calls": [], "answer": "blocked"})])
    _, _, receipts = run_apex_tools(lambda *_: (next(denied), 1),
                                    [{"role": "user", "content": replies_first}],
                                    lambda: True, lambda _: None)
    assert receipts[0]["status"] == "denied"


def test_read_step_numbers_each_sentence_of_the_description(alm):
    step = alm["projects"].add_step(alm["project"], "T: multi part",
                                    description="Search core/x.py for the limit. Report it. Next, run the test.",
                                    owner="apex")
    result = apex_alm.read_step(step)
    assert result["checklist"] == ["1. Search core/x.py for the limit.", "2. Report it.", "3. Next, run the test."]
    assert "description" not in result and "exact paths" in result["checklist_note"]
    assert apex_alm.read_step(alm["step"])["checklist"] == ["1. Use tests/"]
