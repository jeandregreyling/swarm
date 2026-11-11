import json
import subprocess

import pytest

from core import apex_test_runner
from core.apex_tools import TURN_FORMAT, run_apex_tools


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(
        "import os\n"
        "def test_ok():\n    assert True\n"
        "def test_bad():\n    assert 1 == 2\n"
        "def test_isolated():\n"
        "    assert os.environ['SWARM_DB'].startswith(os.environ['HOME'])\n"
        "    assert 'SECRET_TOKEN' not in os.environ\n")
    (tmp_path / "tests" / "test_untracked.py").write_text("def test_x():\n    pass\n")
    (tmp_path / "tests" / "helper.py").write_text("")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "tests/test_sample.py", "tests/helper.py"], check=True)
    return tmp_path


def test_runs_selected_tracked_tests_in_isolated_environment(repo, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "do-not-leak")
    result = apex_test_runner.run_tests({"tests": ["tests/test_sample.py"]}, root=repo)
    assert result["status"] == "failed" and result["exit_code"] == 1
    assert result["verdict"].startswith("FAIL: 1 failed, 2 passed")
    assert next(iter(result)) == "verdict"
    assert "1 failed, 2 passed" in result["summary"]
    assert "test_bad" in result["output_tail"] and "do-not-leak" not in result["output_tail"]
    passed = apex_test_runner.run_tests(
        {"tests": ["tests/test_sample.py"], "keyword": "ok or isolated"}, root=repo)
    assert passed["status"] == "passed" and passed["summary"].startswith("2 passed")
    assert passed["verdict"].startswith("PASS: 2 passed")


def test_empty_selection_is_reported_as_not_a_pass(repo):
    result = apex_test_runner.run_tests(
        {"tests": ["tests/test_sample.py"], "keyword": "no_such_test_name"}, root=repo)
    assert result["exit_code"] == 5 and result["status"] == "failed"
    assert result["verdict"].startswith("NOT A PASS: no tests ran")


@pytest.mark.parametrize("args", [
    {"tests": ["tests/helper.py"]},
    {"tests": ["tests/../tests/test_sample.py"]},
    {"tests": ["/etc/passwd"]},
])
def test_rejects_non_test_or_escaped_paths(repo, args):
    with pytest.raises(PermissionError):
        apex_test_runner.run_tests(args, root=repo)


@pytest.mark.parametrize("args", [
    {}, {"tests": []}, {"tests": "tests/test_sample.py"},
    {"tests": [f"tests/test_{i}.py" for i in range(6)]},
    {"tests": ["tests/test_sample.py", "tests/test_sample.py"]},
    {"tests": ["tests/test_sample.py"], "keyword": "ok; rm -rf /"},
    {"tests": ["tests/test_sample.py"], "keyword": "A"},
    {"tests": ["tests/test_sample.py"], "keyword": " B "},
    {"tests": ["tests/test_sample.py"], "extra": "--pdb"},
])
def test_rejects_invalid_arguments(repo, args):
    with pytest.raises(ValueError):
        apex_test_runner.run_tests(args, root=repo)


def test_case_letter_keyword_points_to_case_id(repo):
    with pytest.raises(ValueError, match="resend them without keyword and with case_id") as error:
        apex_test_runner.validate_test_args({"tests": ["tests/test_sample.py"], "keyword": "A"}, root=repo)
    assert 'titled "A: ..."' in str(error.value)


def test_node_id_is_corrected_to_file_plus_keyword_without_running(repo):
    with pytest.raises(ValueError) as error:
        apex_test_runner.run_tests({"tests": ["tests/test_sample.py::test_ok"]}, root=repo)
    assert '{"tests":["tests/test_sample.py"],"keyword":"test_ok"}' in str(error.value)


@pytest.mark.parametrize("keyword, hint", [
    ("<real_test_name>", "call grep_repo alone"),
    ('""', "only quotes"),
    ("ok; rm", "1-100 letters"),
])
def test_rejected_keywords_explain_the_fix_and_that_nothing_ran(repo, keyword, hint):
    with pytest.raises(ValueError) as error:
        apex_test_runner.validate_test_args({"tests": ["tests/test_sample.py"], "keyword": keyword}, root=repo)
    assert hint in str(error.value)
    assert str(error.value).endswith(apex_test_runner.NOT_RUN)


def test_busy_and_timeout_report_unknown_results(repo, monkeypatch):
    assert apex_test_runner._LOCK.acquire(blocking=False)
    try:
        busy = apex_test_runner.run_tests({"tests": ["tests/test_sample.py"]}, root=repo)
        assert busy["status"] == "busy" and busy["verdict"].startswith("UNKNOWN")
    finally:
        apex_test_runner._LOCK.release()

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("pytest", 1)
    monkeypatch.setattr(apex_test_runner.subprocess, "run", lambda cmd, **kw: (
        timeout() if "pytest" in cmd else subprocess.CompletedProcess(cmd, 0, "tests/test_sample.py\0", "")))
    timed_out = apex_test_runner.run_tests({"tests": ["tests/test_sample.py"]}, root=repo)
    assert timed_out["status"] == "timeout" and timed_out["verdict"].startswith("UNKNOWN")


def test_tool_schema_and_dispatch_require_attached_handler():
    schema = TURN_FORMAT["json_schema"]["schema"]["oneOf"][0]["properties"]["tool_calls"]["items"]["oneOf"]
    call = next(item for item in schema if item["properties"]["name"]["const"] == "run_tests")
    assert call["properties"]["arguments"]["required"] == ["tests"]
    assert call["properties"]["arguments"]["additionalProperties"] is False
    for attached in (False, True):
        outputs = iter([
            json.dumps({"tool_calls": [{"name": "run_tests",
                                        "arguments": {"tests": ["tests/test_x.py"]}}], "answer": ""}),
            json.dumps({"tool_calls": [], "answer": "Reported actual test receipt."}),
        ])
        handler = (lambda args: {"status": "passed", "tests": args["tests"]}) if attached else None
        _, _, receipts = run_apex_tools(
            lambda *_: (next(outputs), 1), [{"role": "user", "content": "Run tests"}],
            lambda: True, lambda _: None, test_handler=handler)
        assert receipts[0]["status"] == ("succeeded" if attached else "denied")


def test_new_nonignored_test_source_is_runnable_without_git_staging(repo):
    result=apex_test_runner.run_tests({'tests':['tests/test_untracked.py']},root=repo)
    assert result['status']=='passed' and result['summary'].startswith('1 passed')


def test_ignored_tests_are_not_executable_through_runner(repo):
    (repo/'.gitignore').write_text('tests/test_ignored.py\n')
    (repo/'tests/test_ignored.py').write_text('def test_x(): pass\n')
    with pytest.raises(PermissionError):apex_test_runner.validate_test_args({'tests':['tests/test_ignored.py']},root=repo)
