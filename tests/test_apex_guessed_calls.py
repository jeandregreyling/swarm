import json
import subprocess

import pytest

from core.apex_tools import ReadOnlyRepository, guessed_test_keyword, run_apex_tools


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "test_sample.py").write_text("def test_real_name():\n    pass\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "test_sample.py"], check=True)
    return ReadOnlyRepository(tmp_path)


def turns(*payloads):
    replies = iter(payloads)

    def model(_name, _messages):
        return json.dumps(next(replies)), 1
    return model


def run_tests(keyword):
    return {"name": "run_tests", "arguments": {"tests": ["test_sample.py"], "keyword": keyword}}


GREP = {"name": "grep_repo", "arguments": {"query": "def test_", "path": "."}}
DONE = {"tool_calls": [], "answer": "Done from receipts."}


@pytest.mark.parametrize("keyword, seen, expected", [
    ("test_root_cause", "grep found test_real_name", "test_root_cause"),
    ("test_real_name", "grep found test_real_name", None),
    ("nonexistent", "", None),
    (None, "", None),
])
def test_guessed_keyword_detection(keyword, seen, expected):
    assert guessed_test_keyword({"keyword": keyword}, seen) == expected


def test_keyword_batched_with_its_grep_is_rejected_before_pytest(repository):
    ran = []
    model = turns({"tool_calls": [GREP, run_tests("test_root_cause")], "answer": ""}, DONE)
    _, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Find and run a test"}],
                                    lambda: True, lambda _: None, repository,
                                    test_handler=lambda args: ran.append(args) or {"verdict": "PASS"})
    assert ran == []
    assert receipts[1]["status"] == "failed"
    output = receipts[1]["output"]
    assert output.startswith("GUESS: keyword 'test_root_cause' appears in no earlier receipt")
    assert "Your receipts this turn show test functions test_real_name." in output
    assert "use a keyword not starting with test_" in output and "NOT RUN: no pytest started" in output


def test_untracked_test_path_becomes_a_fixable_failure_listing_seen_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_real.py").write_text("def test_real_name():\n    pass\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tests/test_real.py"], check=True)
    repository = ReadOnlyRepository(tmp_path)

    def handler(args):
        raise PermissionError(f"Not a tracked tests/test_*.py file: {args['tests'][0]!r} NOT RUN: nothing ran.")
    grep = {"name": "grep_repo", "arguments": {"query": "def test_", "path": "tests"}}
    guess = {"name": "run_tests", "arguments": {"tests": ["tests/test_invented.py"]}}
    model = turns({"tool_calls": [grep, guess], "answer": ""}, DONE)
    _, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Run the real test"}],
                                    lambda: True, lambda _: None, repository, test_handler=handler)
    assert receipts[1]["status"] == "failed"
    assert ("Your receipts this turn show test files tests/test_real.py; test functions test_real_name. "
            "Choose the one the task asks for") in receipts[1]["output"]
    assert receipts[1]["output"].endswith("NOT RUN: nothing ran.")


def test_keyword_copied_from_an_earlier_receipt_runs(repository):
    ran = []
    model = turns({"tool_calls": [GREP], "answer": ""},
                  {"tool_calls": [run_tests("test_real_name")], "answer": ""}, DONE)
    _, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Find and run a test"}],
                                    lambda: True, lambda _: None, repository,
                                    test_handler=lambda args: ran.append(args) or {"verdict": "PASS"})
    assert ran == [{"tests": ["test_sample.py"], "keyword": "test_real_name"}]
    assert [receipt["status"] for receipt in receipts] == ["succeeded", "succeeded"]


def test_repeating_a_rejected_call_explains_it_cannot_succeed(repository):
    bad = {"name": "read_file", "arguments": {"path": "../outside.py"}}
    model = turns({"tool_calls": [bad], "answer": ""}, {"tool_calls": [bad], "answer": ""}, DONE)
    _, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Read it"}],
                                    lambda: True, lambda _: None, repository)
    first, second = receipts
    assert first["status"] in {"failed", "denied"}
    assert second["status"] == "failed"
    assert second["output"].startswith(f"REPEATED CALL: receipt {first['id']} already rejected")
    assert "Repeating it cannot succeed" in second["output"]


def test_step_answer_after_only_rejected_test_runs_gets_one_fixed_call_correction(repository):
    ran = []
    step = {"name": "alm_step_get", "arguments": {"step_id": "S-52E4074AF1"}}
    fixed = {"name": "run_tests", "arguments": {"tests": ["test_sample.py"], "keyword": "test_real_name",
                                                "case_id": "C-5E4276FA43"}}
    seen = []

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        replies = [{"tool_calls": [step], "answer": ""},
                   {"tool_calls": [GREP, run_tests("test_root_cause")], "answer": ""},
                   {"tool_calls": [], "answer": "grep_repo succeeded. run_tests failed."},
                   {"tool_calls": [fixed], "answer": ""},
                   {"tool_calls": [], "answer": "test_real_name PASS."}]
        return json.dumps(replies[len(seen) - 1]), 1

    text, _, receipts = run_apex_tools(
        model, [{"role": "user", "content": "Your next ALM step is S-52E4074AF1."}], lambda: True,
        lambda _: None, repository, studio_handler=lambda name, args: {"status": "found"},
        test_handler=lambda args: ran.append(args) or {"verdict": "PASS"})
    assert seen[3].startswith("BACKEND STEP CHECK") and receipts[2]["id"] in seen[3]
    assert ran == [fixed["arguments"]] and text == "test_real_name PASS."


def test_rejected_test_run_report_is_delivered_without_a_step_or_after_a_real_run(repository):
    model = turns({"tool_calls": [GREP, run_tests("test_root_cause")], "answer": ""},
                  {"tool_calls": [], "answer": "run_tests failed."})
    text, _, _ = run_apex_tools(model, [{"role": "user", "content": "Run a test"}], lambda: True,
                                lambda _: None, repository, studio_handler=lambda name, args: {"status": "found"},
                                test_handler=lambda args: {"verdict": "PASS"})
    assert text == "run_tests failed."


def test_phrase_grep_with_few_matches_suggests_one_word_and_single_words_get_no_hint(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "settings.py").write_text('MAX_ROUNDS = 6\nNOTICE = "used all its tool rounds"\n')
    subprocess.run(["git", "-C", str(tmp_path), "add", "settings.py"], check=True)
    repository = ReadOnlyRepository(tmp_path)
    phrase = repository.call("grep_repo", {"query": "tool rounds", "path": "."})
    assert "settings.py:2:" in phrase and "settings.py:1:" not in phrase
    assert "search one word alone, e.g. 'rounds'" in phrase
    word = repository.call("grep_repo", {"query": "rounds", "path": "."})
    assert "settings.py:1: MAX_ROUNDS = 6" in word and "one word alone" not in word
    guessed = repository.call("grep_repo", {"query": "tool_rounds", "path": "."})
    assert "only 0 match(es) for 'tool_rounds'" in guessed and "e.g. 'rounds'" in guessed
    exact = repository.call("grep_repo", {"query": "MAX_ROUNDS", "path": "."})
    assert "settings.py:1:" in exact and "one word alone" not in exact
    case = repository.call("grep_repo", {"query": "C-9C430774C9", "path": "."})
    assert "only 0 match(es)" not in case and "[complete:" in case


STEP_REQUEST = [{"role": "user", "content": "Your next ALM step is S-ABCDEF1234. Run test_real_name."}]
STEP_GET = {"name": "alm_step_get", "arguments": {"step_id": "S-ABCDEF1234"}}
RECORDED = {"name": "run_tests", "arguments": {"tests": ["test_sample.py"], "keyword": "test_real_name",
                                               "case_id": "C-1"}}
RUN_RESULT = {"verdict": "PASS: 1 passed", "alm_run_id": "0123456789abcdef", "status": "passed"}


def recording(*payloads):
    seen = []
    replies = iter(payloads)

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        return json.dumps(next(replies)), 1
    return model, seen


def run_step(model, repository):
    return run_apex_tools(model, STEP_REQUEST, lambda: True, lambda _: None, repository,
                          studio_handler=lambda name, args: {"status": "found", "project_id": "P-1"},
                          test_handler=lambda args: dict(RUN_RESULT))


def test_answer_denying_a_recorded_run_gets_one_answer_only_correction(repository):
    reported = {"tool_calls": [], "answer": "PASS: 1 passed, ALM run 0123456789abcdef."}
    model, seen = recording({"tool_calls": [STEP_GET], "answer": ""}, {"tool_calls": [RECORDED], "answer": ""},
                            {"tool_calls": [], "answer": "The test execution step was not performed."}, reported)
    text, _, receipts = run_step(model, repository)
    assert text == reported["answer"] and len(receipts) == 2
    correction = seen[-1]
    assert correction.startswith("BACKEND RECEIPT CHECK: your answer was not delivered.")
    assert f"run_tests receipt {receipts[1]['id']} DID run pytest this turn: PASS: 1 passed, " \
           "ALM run 0123456789abcdef" in correction and "with no tool calls" in correction


def test_recorded_run_correction_still_fires_after_the_round_limit(repository):
    from core.apex_tools import MAX_ROUNDS, ROUND_LIMIT_NOTICE
    status = {"tool_calls": [{"name": "git_status", "arguments": {}}], "answer": ""}
    model, seen = recording({"tool_calls": [STEP_GET], "answer": ""}, {"tool_calls": [RECORDED], "answer": ""},
                            *[status] * (MAX_ROUNDS - 2),
                            {"tool_calls": [], "answer": "Could not finish the step."},
                            {"tool_calls": [], "answer": "Ran it: ALM run 0123456789abcdef passed."})
    text, _, _ = run_step(model, repository)
    assert text == "Ran it: ALM run 0123456789abcdef passed."
    assert len(seen) == MAX_ROUNDS + 2 and seen[-2] == ROUND_LIMIT_NOTICE
    assert seen[-1].startswith("BACKEND RECEIPT CHECK")


def test_persistent_omission_is_delivered_with_a_backend_note_and_tools_stay_closed(repository):
    model, _ = recording({"tool_calls": [STEP_GET], "answer": ""}, {"tool_calls": [RECORDED], "answer": ""},
                         {"tool_calls": [], "answer": "No test ran."}, {"tool_calls": [], "answer": "No test ran."})
    text, _, receipts = run_step(model, repository)
    assert text.startswith("No test ran.\n[Backend receipt check: run_tests receipt ")
    assert "ALM run 0123456789abcdef, which this answer omits]" in text and len(receipts) == 2
    model, _ = recording({"tool_calls": [STEP_GET], "answer": ""}, {"tool_calls": [RECORDED], "answer": ""},
                         {"tool_calls": [], "answer": "No test ran."}, {"tool_calls": [RECORDED], "answer": ""})
    text, _, receipts = run_step(model, repository)
    assert "asked for more tools after a receipt check asked only for an answer" in text
    assert [receipt["tool"] for receipt in receipts] == ["alm_step_get", "run_tests", "studio_handoff"]


def test_corrected_answer_is_kept_so_its_receipts_compact_but_it_grounds_nothing(repository):
    from core.apex_context import ARCHIVED_RECEIPTS_HEADER, prepare_context
    snapshots = []
    replies = iter([{"tool_calls": [STEP_GET], "answer": ""},
                    {"tool_calls": [{"name": "run_tests", "arguments": {
                        "tests": ["test_sample.py"], "keyword": "test_first_guess", "case_id": "C-1"}}], "answer": ""},
                    {"tool_calls": [], "answer": "Blocked: test_made_up was not run."},
                    {"tool_calls": [{"name": "run_tests", "arguments": {
                        "tests": ["test_sample.py"], "keyword": "test_made_up", "case_id": "C-1"}}], "answer": ""},
                    {"tool_calls": [], "answer": "Not run: no such test."}])

    def model(_name, messages):
        snapshots.append([dict(message) for message in messages])
        return json.dumps(next(replies)), 1
    _, _, receipts = run_step(model, repository)
    corrected = snapshots[3]
    assert corrected[-1]["content"].startswith("BACKEND STEP CHECK")
    assert corrected[-2] == {"role": "assistant", "content": "Blocked: test_made_up was not run.",
                             "rejected_answer": True}
    compacted = prepare_context(corrected, lambda messages: 1)
    assert any(message["content"].startswith(ARCHIVED_RECEIPTS_HEADER) for message in compacted)
    assert receipts[-1]["output"].startswith("GUESS: keyword 'test_made_up' appears in no earlier receipt")


def test_step_answer_skipping_named_searches_gets_one_correction_listing_them(tmp_path):
    from core.apex_tools import skipped_searches
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "core").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "core" / "limits.py").write_text("MAX_ROUNDS = 6\n")
    (tmp_path / "tests" / "test_limits.py").write_text("def test_calls_are_bounded():\n    pass\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    repository = ReadOnlyRepository(tmp_path)
    checklist = ["1. Designed with Gemini.", "2. Search the core path to find the round setting.",
                 "3. Next, search the tests path for the word bounded to locate the test."]
    core = {"name": "grep_repo", "arguments": {"query": "rounds", "path": "core/"}}
    bounded = {"name": "grep_repo", "arguments": {"query": "bounded", "path": "./tests"}}
    wrong = {"name": "grep_repo", "arguments": {"query": "bounded", "path": "."}}
    model, seen = recording({"tool_calls": [STEP_GET], "answer": ""}, {"tool_calls": [wrong], "answer": ""},
                            {"tool_calls": [], "answer": "Nothing found."},
                            {"tool_calls": [core, bounded], "answer": ""},
                            {"tool_calls": [], "answer": "core/limits.py:1 MAX_ROUNDS = 6."})
    text, _, receipts = run_apex_tools(model, STEP_REQUEST, lambda: True, lambda _: None, repository,
                                       studio_handler=lambda name, args: {"status": "found", "checklist": checklist})
    correction = seen[3]
    assert correction.startswith("BACKEND STEP CHECK") and "S-ABCDEF1234" in correction
    assert "checklist item 2 needs a search with path 'core'" in correction
    assert "checklist item 3 needs a search with path 'tests' and word 'bounded'" in correction
    assert text == "core/limits.py:1 MAX_ROUNDS = 6." and skipped_searches(receipts) == []
