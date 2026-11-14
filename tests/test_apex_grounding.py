import json
import subprocess

import pytest

from core.apex_tools import ReadOnlyRepository, run_apex_tools, ungrounded_ids


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "sample.py").write_text("hello\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.py"], check=True)
    return ReadOnlyRepository(tmp_path)


def answer(text):
    return json.dumps({"tool_calls": [], "answer": text})


def scripted(*replies):
    seen = []

    def model(_name, messages):
        seen.append([dict(message) for message in messages])
        reply = replies[len(seen) - 1]
        return (reply(messages) if callable(reply) else reply), 1
    return model, seen


def test_ungrounded_ids_normalises_hyphens_and_case():
    seen = "step S-BDFBE93AED run 3a85047ac35a4fd9"
    assert ungrounded_ids("s-bdfbe93aed and 3A85047AC35A4FD9", seen) == []
    assert ungrounded_ids("case C\u20111111111111", seen) == ["C-1111111111"]


def test_invented_ids_get_one_grounded_retry(repository):
    model, seen = scripted(answer("Run R-1234567890 failed; case C-1111111111 passed."),
                           answer("I have not read the step yet; no run is verified."))
    request = [{"role": "user", "content": "Report step S-BDFBE93AED."}]
    text, _, receipts = run_apex_tools(model, request, lambda: True, lambda _: None, repository)
    assert text == "I have not read the step yet; no run is verified." and not receipts
    correction = seen[1][-1]["content"]
    assert correction.startswith("BACKEND GROUNDING ERROR")
    assert "R-1234567890" in correction and "C-1111111111" in correction


def test_ids_from_request_and_receipts_are_accepted(repository):
    def cite_receipt(messages):
        receipt_id = json.loads(messages[-1]["content"].split("\n", 1)[1].split("\nUse these", 1)[0])[0]["id"]
        return answer(f"Step S-BDFBE93AED: git_status receipt {receipt_id} succeeded.")
    model, seen = scripted(json.dumps({"tool_calls": [{"name": "git_status", "arguments": {}}],
                                       "answer": ""}), cite_receipt)
    request = [{"role": "user", "content": "Check S-BDFBE93AED."}]
    text, _, receipts = run_apex_tools(model, request, lambda: True, lambda _: None, repository)
    assert receipts[0]["id"] in text and "grounding" not in text and len(seen) == 2


def test_persisting_invented_ids_are_delivered_with_a_visible_warning(repository):
    invented = answer("Case C-1111111111 passed.")
    model, seen = scripted(invented, invented)
    text, _, _ = run_apex_tools(model, [{"role": "user", "content": "Status?"}],
                                lambda: True, lambda _: None, repository)
    assert len(seen) == 2
    assert text.startswith("Case C-1111111111 passed.")
    assert "[Backend grounding warning" in text and text.endswith("C-1111111111]")


def studio_reads(calls):
    def studio(name, arguments):
        calls.append((name, arguments))
        return {"status": "found", "step_id": arguments["step_id"], "description": "run case A"}
    return studio


def test_requested_step_claimed_without_a_read_gets_one_read_correction(repository):
    calls = []
    model, seen = scripted(
        answer("I have retrieved the details for ALM step S-23F6ADA690. What should I do next?"),
        json.dumps({"tool_calls": [{"name": "alm_step_get", "arguments": {"step_id": "S-23F6ADA690"}}],
                    "answer": ""}),
        answer("Step S-23F6ADA690 asks me to run case A."))
    request = [{"role": "user", "content": "Retest ALM step S-23F6ADA690. Read it with alm_step_get."}]
    text, _, receipts = run_apex_tools(model, request, lambda: True, lambda _: None, repository,
                                       studio_handler=studio_reads(calls))
    correction = seen[1][-1]["content"]
    assert correction.startswith("BACKEND STEP CHECK") and "S-23F6ADA690" in correction
    assert calls == [("alm_step_get", {"step_id": "S-23F6ADA690"})]
    assert text == "Step S-23F6ADA690 asks me to run case A."
    assert [receipt["tool"] for receipt in receipts] == ["alm_step_get"]


def test_step_check_warns_when_the_read_never_happens_and_skips_without_studio(repository):
    lazy = answer("I already read S-23F6ADA690.")
    model, seen = scripted(lazy, lazy)
    request = [{"role": "user", "content": "Do step S-23F6ADA690."}]
    text, _, _ = run_apex_tools(model, request, lambda: True, lambda _: None, repository,
                                studio_handler=studio_reads([]))
    assert len(seen) == 2 and "[Backend step check: ALM step S-23F6ADA690 was never read" in text
    model, seen = scripted(lazy)
    text, _, _ = run_apex_tools(model, request, lambda: True, lambda _: None, repository)
    assert text == "I already read S-23F6ADA690." and len(seen) == 1


def test_misattributed_receipt_ids_are_found_per_line():
    from core.apex_tools import misattributed_receipts
    receipts = [{"id": "a" * 32, "tool": "alm_step_get"}, {"id": "b" * 32, "tool": "git_status"},
                {"id": "c" * 32, "tool": "grep_repo"}]
    report = (f"alm_step_get: ok (receipt id {'b' * 32})\n"
              f"git_status: ok (receipt id {'b' * 32})\n"
              f"grep_repo and git_status together: {'a' * 32}")
    problems = misattributed_receipts(report, receipts)
    assert problems == [f"alm_step_get is paired with receipt {'b' * 32}, which is the git_status "
                        f"receipt; alm_step_get receipt(s) this turn: {'a' * 32}"]


def test_receipt_paired_with_the_wrong_tool_gets_one_corrective_retry(repository):
    status_call = json.dumps({"tool_calls": [{"name": "git_status", "arguments": {}},
                                             {"name": "list_files", "arguments": {"path": "."}}],
                              "answer": ""})

    def wrong(messages):
        receipts = json.loads(messages[-1]["content"].split("\n", 1)[1].split("\nUse these results", 1)[0])
        return answer(f"git_status: ok (receipt id {receipts[1]['id']})")

    def right(messages):
        assert messages[-1]["content"].startswith("BACKEND RECEIPT CHECK")
        status_id = messages[-1]["content"].split("git_status receipt(s) this turn: ", 1)[1][:32]
        return answer(f"git_status: ok (receipt id {status_id})")

    model, seen = scripted(status_call, wrong, right)
    text, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Check status"}],
                                       lambda: True, lambda _: None, repository)
    assert len(seen) == 3
    assert text == f"git_status: ok (receipt id {receipts[0]['id']})"


def test_step_answer_citing_an_earlier_turns_receipt_must_run_the_tool_now(repository):
    stale = "5" * 32
    history = [{"role": "assistant", "content": f"git_status, ok, {stale}"},
               {"role": "user", "content": "Retest ALM step S-8CD493D774."}]
    step_call = json.dumps({"tool_calls": [{"name": "alm_step_get",
                                            "arguments": {"step_id": "S-8CD493D774"}}], "answer": ""})
    status_call = json.dumps({"tool_calls": [{"name": "git_status", "arguments": {}}], "answer": ""})

    def fresh(messages):
        receipts = json.loads(messages[-1]["content"].split("\n", 1)[1].split("\nUse these results", 1)[0])
        return answer(f"git_status, ok, {receipts[0]['id']}")

    def check_feedback(messages):
        assert messages[-1]["content"].startswith("BACKEND RECEIPT CHECK")
        assert f"receipt(s) {stale} come from earlier context" in messages[-1]["content"]
        return status_call

    model, seen = scripted(step_call, answer(f"git_status, ok, {stale}"), check_feedback, fresh)
    text, _, receipts = run_apex_tools(model, history, lambda: True, lambda _: None, repository,
                                       studio_handler=lambda name, args: {"status": "found"})
    assert [receipt["tool"] for receipt in receipts] == ["alm_step_get", "git_status"]
    assert text == f"git_status, ok, {receipts[1]['id']}"


def test_earlier_receipts_may_be_cited_when_no_step_is_being_run(repository):
    stale = "6" * 32
    history = [{"role": "assistant", "content": f"git_status, ok, {stale}"},
               {"role": "user", "content": "Which receipt did git_status have last time?"}]
    model, seen = scripted(answer(f"It was {stale}."))
    text, _, _ = run_apex_tools(model, history, lambda: True, lambda _: None, repository,
                                studio_handler=lambda name, args: {"status": "found"})
    assert text == f"It was {stale}." and len(seen) == 1


def test_step_answer_asking_the_operator_for_findable_input_gets_one_work_correction(repository):
    step_call = json.dumps({"tool_calls": [{"name": "alm_step_get",
                                            "arguments": {"step_id": "S-5B27590041"}}], "answer": ""})
    grep_call = json.dumps({"tool_calls": [{"name": "grep_repo",
                                            "arguments": {"query": "hello", "path": "."}}], "answer": ""})

    def correction(messages):
        content = messages[-1]["content"]
        assert content.startswith("BACKEND STEP CHECK") and "S-5B27590041" in content
        assert "call grep_repo alone" in content
        return grep_call

    request = [{"role": "user", "content": "Retest ALM step S-5B27590041. Do it exactly as written."}]
    model, seen = scripted(step_call,
                           answer("I\u2019m sorry, but I can\u2019t proceed without the test file. Please provide the path."),
                           correction, answer("sample.py:1 has hello."))
    text, _, receipts = run_apex_tools(model, request, lambda: True, lambda _: None, repository,
                                       studio_handler=lambda name, args: {"status": "found"})
    assert [receipt["tool"] for receipt in receipts] == ["alm_step_get", "grep_repo"]
    assert text == "sample.py:1 has hello."


def test_asking_for_help_is_delivered_after_a_blocking_receipt_or_without_a_step(repository):
    give_up = answer("I cannot proceed; please provide the path.")
    denied_call = json.dumps({"tool_calls": [{"name": "read_file",
                                              "arguments": {"path": "../outside.txt"}}], "answer": ""})
    request = [{"role": "user", "content": "Do step S-5B27590041."}]
    step_call = json.dumps({"tool_calls": [{"name": "alm_step_get",
                                            "arguments": {"step_id": "S-5B27590041"}}], "answer": ""})
    model, seen = scripted(step_call, denied_call, give_up)
    text, _, receipts = run_apex_tools(model, request, lambda: True, lambda _: None, repository,
                                       studio_handler=lambda name, args: {"status": "found"})
    assert receipts[1]["status"] in {"failed", "denied"}
    assert text == "I cannot proceed; please provide the path." and len(seen) == 3
    model, seen = scripted(give_up)
    text, _, _ = run_apex_tools(model, [{"role": "user", "content": "What file?"}],
                                lambda: True, lambda _: None, repository,
                                studio_handler=lambda name, args: {"status": "found"})
    assert text == "I cannot proceed; please provide the path." and len(seen) == 1


def test_deflecting_a_requested_value_after_a_fixed_failure_gets_the_work_correction(repository):
    step_call = json.dumps({"tool_calls": [{"name": "alm_step_get",
                                            "arguments": {"step_id": "S-242C8AE6A3"}}], "answer": ""})
    bad_read = json.dumps({"tool_calls": [{"name": "read_file", "arguments": {"path": "missing.py"}}],
                           "answer": ""})
    good_read = json.dumps({"tool_calls": [{"name": "read_file", "arguments": {"path": "sample.py"}}],
                            "answer": ""})
    deflect = answer("Value: not directly visible; it is defined elsewhere (search MAX to locate it).")

    def correction(messages):
        assert messages[-1]["content"].startswith("BACKEND STEP CHECK")
        assert "one distinctive word" in messages[-1]["content"]
        return answer("sample.py:1 says hello.")

    request = [{"role": "user", "content": "Your next ALM step is S-242C8AE6A3."}]
    model, seen = scripted(step_call, bad_read, good_read, deflect, correction)
    text, _, receipts = run_apex_tools(model, request, lambda: True, lambda _: None, repository,
                                       studio_handler=lambda name, args: {"status": "found"})
    # A missing source path is a recoverable lookup failure, not a permission denial.
    assert [receipt["status"] for receipt in receipts] == ["succeeded", "failed", "succeeded"]
    assert text == "sample.py:1 says hello." and len(seen) == 5
