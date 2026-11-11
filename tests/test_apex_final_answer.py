import json
import subprocess

import pytest

from core.apex_context import (CONTEXT_TOKENS, FINAL_ANSWER_RESERVE, OUTPUT_RESERVE, final_answer_reserve,
                               generation_budget, output_reserve, prepare_context)
from core.apex_tools import FINAL_ANSWER_NOTICE, ReadOnlyRepository, run_apex_tools

STATUS_CALL = json.dumps({"tool_calls": [{"name": "git_status", "arguments": {}}], "answer": ""})


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "sample.py").write_text("hello\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.py"], check=True)
    return ReadOnlyRepository(tmp_path)


def no_capacity_handoff(name, _arguments):
    pytest.fail(f"Unexpected Studio call {name}")


def full_unless_final(working, batch):
    if output_reserve() != FINAL_ANSWER_RESERVE:
        raise RuntimeError("APEX context cannot fit even the read-budget warning; no further inference submitted")
    return batch


def test_reserve_scope_admits_a_short_final_answer_only_inside_it():
    messages = [{"role": "user", "content": "x"}]
    tight = CONTEXT_TOKENS - FINAL_ANSWER_RESERVE
    with pytest.raises(RuntimeError, match=f"reserve {OUTPUT_RESERVE}"):
        prepare_context(messages, lambda _: tight)
    with final_answer_reserve():
        assert prepare_context(messages, lambda _: tight) == messages
        assert generation_budget(messages, lambda _: tight) == FINAL_ANSWER_RESERVE
        with pytest.raises(RuntimeError, match=f"reserve {FINAL_ANSWER_RESERVE}"):
            prepare_context(messages, lambda _: tight + 1)
    assert output_reserve() == OUTPUT_RESERVE


def test_window_filled_by_receipts_gets_one_tool_free_final_answer(repository):
    seen = []

    def model(_name, messages):
        seen.append((output_reserve(), messages[-1]["content"]))
        if len(seen) == 1:
            return STATUS_CALL, 1
        return json.dumps({"tool_calls": [], "answer": "git_status succeeded; nothing unfinished."}), 1

    text, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Check status"}],
                                       lambda: True, lambda _: None, repository,
                                       prepare_receipts=full_unless_final,
                                       studio_handler=no_capacity_handoff)
    assert text == "git_status succeeded; nothing unfinished."
    assert [receipt["tool"] for receipt in receipts] == ["git_status"]
    assert seen[0][0] == OUTPUT_RESERVE
    assert seen[1] == (FINAL_ANSWER_RESERVE, FINAL_ANSWER_NOTICE)


def test_window_full_before_inference_after_tools_still_gets_the_final_round(repository):
    prepared, seen = [], []

    def prepare(working):
        prepared.append(output_reserve())
        if len(prepared) == 2:
            raise RuntimeError("APEX context budget exceeded: 5200 prompt tokens, limit 5120")
        return working

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        if len(seen) == 1:
            return STATUS_CALL, 1
        return json.dumps({"tool_calls": [], "answer": "Status read; report complete."}), 1

    text, _, _ = run_apex_tools(model, [{"role": "user", "content": "Check status"}],
                                lambda: True, lambda _: None, repository,
                                prepare_messages=prepare, studio_handler=no_capacity_handoff)
    assert text == "Status read; report complete."
    assert prepared == [OUTPUT_RESERVE, OUTPUT_RESERVE, FINAL_ANSWER_RESERVE]
    assert seen[-1] == FINAL_ANSWER_NOTICE


def test_more_tools_after_the_window_filled_saves_a_handoff_without_running_them(repository):
    handoffs = []

    def studio(name, arguments):
        handoffs.append((name, arguments["summary"]))
        return {"project_id": "P-FULL"}

    calls = []

    def model(_name, _messages):
        calls.append(1)
        return STATUS_CALL, 1

    text, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Check status"}],
                                       lambda: True, lambda _: None, repository,
                                       prepare_receipts=full_unless_final, studio_handler=studio)
    assert len(calls) == 2 and "P-FULL" in text
    assert handoffs == [("studio_capacity_handoff",
                         "APEX asked for more tools after its context window filled")]
    assert [receipt["tool"] for receipt in receipts] == ["git_status", "studio_handoff"]


def test_round_limit_after_tool_work_gets_one_tool_free_final_answer(repository):
    from core.apex_tools import MAX_ROUNDS, ROUND_LIMIT_NOTICE
    seen = []

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        if len(seen) <= MAX_ROUNDS:
            return STATUS_CALL, 1
        return json.dumps({"tool_calls": [], "answer": "git_status succeeded every round."}), 1

    text, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Check status"}],
                                       lambda: True, lambda _: None, repository,
                                       studio_handler=no_capacity_handoff)
    assert text == "git_status succeeded every round."
    assert len(receipts) == MAX_ROUNDS and seen[-1] == ROUND_LIMIT_NOTICE


def test_low_remaining_time_after_tool_work_gets_one_tool_free_final_answer(repository, monkeypatch):
    import types

    from core import apex_tools
    now = [0.0]
    monkeypatch.setattr(apex_tools, "time", types.SimpleNamespace(monotonic=lambda: now[0]))
    seen = []

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        if len(seen) == 1:
            now[0] = apex_tools.TURN_SECONDS - apex_tools.FINAL_TIME_RESERVE + 1
            return STATUS_CALL, 1
        return json.dumps({"tool_calls": [], "answer": "git_status succeeded; nothing unfinished."}), 1

    text, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Check status"}],
                                       lambda: True, lambda _: None, repository,
                                       studio_handler=no_capacity_handoff)
    assert text == "git_status succeeded; nothing unfinished."
    assert len(seen) == 2 and seen[-1] == apex_tools.TIME_LIMIT_NOTICE
    assert [receipt["tool"] for receipt in receipts] == ["git_status"]


def test_slow_rounds_stop_tools_while_one_tool_round_and_the_answer_still_fit(repository, monkeypatch):
    import types

    from core import apex_tools
    now = [0.0]
    monkeypatch.setattr(apex_tools, "time", types.SimpleNamespace(monotonic=lambda: now[0]))
    seen = []

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        now[0] += 80
        if messages[-1]["content"] != apex_tools.TIME_LIMIT_NOTICE:
            return STATUS_CALL, 1
        return json.dumps({"tool_calls": [], "answer": "git_status succeeded; nothing unfinished."}), 1

    text, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Check status"}],
                                       lambda: True, lambda _: None, repository,
                                       studio_handler=no_capacity_handoff)
    # 360 s budget: tool rounds start at 0, 80 and 160 s; at 240 s only 120 s remain, under two 80 s rounds.
    assert text == "git_status succeeded; nothing unfinished."
    assert len(receipts) == 3 and seen[-1] == apex_tools.TIME_LIMIT_NOTICE and now[0] <= apex_tools.TURN_SECONDS


def test_repeated_completed_reads_report_saved_evidence_instead_of_studio_handoff(repository):
    """Chat 2834: two real reads, two suppressed duplicates, then another tool request."""
    calls = []
    step = {"name": "alm_step_get", "arguments": {"step_id": "S-D475345C87"}}
    archive = {"name": "archive_status", "arguments": {}}
    outputs = iter([step, archive, archive, archive,
                    {"name": "archive_mirror_resume", "arguments": {}}])

    def model(*_):
        return json.dumps({"tool_calls": [next(outputs)], "answer": ""}), 1

    def studio(name, args):
        calls.append(name)
        if name == "alm_step_get":
            return {"step_id": args["step_id"], "checklist": ["Confirm row/revision citations"]}
        assert name == "archive_status", "Repeated reads must never create a handoff or resume downloads"
        return {"downloads_paused": True, "dataset_rows_processed": 4749234}

    text, _, receipts = run_apex_tools(model, [{"role": "user", "content":
        "Inspect S-D475345C87, compare the archive and index, and report what remains. Keep downloads paused."}],
        lambda: True, lambda _: None, repository, studio_handler=studio)
    assert calls == ["alm_step_get", "archive_status"]
    assert [r["tool"] for r in receipts] == calls
    assert "unfinished" in text.lower()
    assert "4749234" in text and "row/revision citations" in text
    assert all(r["id"] in text for r in receipts)


def test_repeated_read_final_answer_uses_answer_only_schema_and_restores_tool_access(repository):
    from core.apex_tools import TURN_FORMAT, response_format_for_turn
    read = json.dumps({"tool_calls": [{"name": "read_file", "arguments": {"path": "sample.py"}}], "answer": ""})
    formats = []

    def model(_name, messages):
        fmt = response_format_for_turn()
        formats.append(fmt)
        if len(formats) <= 3:
            return read, 1
        schema = fmt["json_schema"]["schema"]
        assert schema["properties"]["tool_calls"]["maxItems"] == 0
        assert schema["properties"]["answer"]["minLength"] == 1
        assert "comparing the existing evidence" in messages[-1]["content"]
        return json.dumps({"tool_calls": [], "answer": "sample.py contains hello; no other files were inspected."}), 1

    text, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Inspect sample.py"}],
        lambda: True, lambda _: None, repository, studio_handler=no_capacity_handoff)
    assert formats[:3] == [TURN_FORMAT] * 3 and len(formats) == 4
    assert len(receipts) == 1 and "no other files" in text
    assert response_format_for_turn() is TURN_FORMAT


def test_final_answer_schema_scope_is_restored_even_when_inference_fails(repository):
    from core.apex_tools import TURN_FORMAT, response_format_for_turn
    calls = []

    def model(*_):
        calls.append(1)
        if len(calls) == 1:
            return STATUS_CALL, 1
        assert response_format_for_turn()["json_schema"]["schema"]["properties"]["tool_calls"]["maxItems"] == 0
        raise RuntimeError("inference failed")

    with pytest.raises(RuntimeError, match="inference failed"):
        run_apex_tools(model, [{"role": "user", "content": "Inspect status"}],
            lambda: True, lambda _: None, repository, prepare_receipts=full_unless_final)
    assert response_format_for_turn() is TURN_FORMAT
    assert output_reserve() == OUTPUT_RESERVE
