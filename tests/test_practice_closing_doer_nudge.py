"""Closing-round doer/promise check and question re-anchoring in core/apex_tools.py.

On 23 Nov 2026 (conv 2848, 09:00), after burning tool rounds on knowledge_search calls for
"what are technical wage types?", APEX hit the closing round and replied with
"I will now read SAP Note 3734455..." — which doer_ok() already flagged as False, but grounded()
skipped because can_retry was False on the closing round.
"""
from __future__ import annotations

import json
import subprocess
import types

import pytest

from core import apex_tools
from core.apex_tools import (
    DOER_CLOSING_NOTICE,
    MAX_ROUNDS,
    ROUND_LIMIT_NOTICE,
    ReadOnlyRepository,
    doer_ok,
    run_apex_tools,
)


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "sample.py").write_text("hello\nworld\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.py"], check=True)
    return ReadOnlyRepository(tmp_path)


def test_doer_ok_catches_i_will_read_and_check_promises():
    receipts = [{"tool": "knowledge_search", "status": "succeeded", "id": "r1"}]
    assert not doer_ok("I will now read SAP Note 3734455 to check SDI wage types.", receipts)
    assert not doer_ok("I will read SAP Note 3734455 next.", receipts)
    assert not doer_ok("I'll check the remaining notes next.", receipts)
    assert doer_ok("Technical wage types (/xxx) are system-generated SAP Payroll wage types.", receipts)


def test_closing_round_bounces_i_will_promise_and_reanchors_question(repository, monkeypatch):
    seen = []
    steps = []
    monkeypatch.setattr(apex_tools, "say_step", steps.append)

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        n = len(seen)
        if n <= MAX_ROUNDS:
            return json.dumps({
                "tool_calls": [{"name": "grep_repo", "arguments": {"query": f"term{n}"}}],
                "answer": "",
            }), 1
        if n == MAX_ROUNDS + 1:
            return json.dumps({
                "tool_calls": [],
                "answer": "I have read note 3734465. I will now read SAP Note 3734455 to check SDI.",
            }), 1
        return json.dumps({
            "tool_calls": [],
            "answer": "Technical wage types (/xxx) are SAP Payroll system wage types like /101 and /560.",
        }), 1

    text, _, receipts = run_apex_tools(
        model,
        [{"role": "user", "content": "what are technical wage types?"}],
        lambda: True,
        lambda _: None,
        repository,
    )
    assert len(receipts) == MAX_ROUNDS
    assert seen[-2] == ROUND_LIMIT_NOTICE
    assert seen[-1] == DOER_CLOSING_NOTICE.format(question="what are technical wage types?")
    assert "Technical wage types (/xxx)" in text
    assert any("doer check sent the answer back" in s for s in steps)


def test_time_limit_closing_round_also_bounces_i_will_promise(repository, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(apex_tools, "time", types.SimpleNamespace(monotonic=lambda: now[0]))
    seen = []

    def model(_name, messages):
        seen.append(messages[-1]["content"])
        if len(seen) == 1:
            now[0] = apex_tools.TURN_SECONDS - apex_tools.FINAL_TIME_RESERVE + 1
            return json.dumps({
                "tool_calls": [{"name": "git_status", "arguments": {}}],
                "answer": "",
            }), 1
        if len(seen) == 2:
            return json.dumps({
                "tool_calls": [],
                "answer": "I will read another note to check.",
            }), 1
        return json.dumps({
            "tool_calls": [],
            "answer": "Technical wage types start with / and are generated automatically during payroll.",
        }), 1

    text, _, _ = run_apex_tools(
        model,
        [{"role": "user", "content": "what are technical wage types?"}],
        lambda: True,
        lambda _: None,
        repository,
    )
    assert seen[1] == apex_tools.TIME_LIMIT_NOTICE
    assert "what are technical wage types?" in seen[2]
    assert "generated automatically during payroll" in text
