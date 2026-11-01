import json
import sys

import pytest
from pydantic import ValidationError

from core.deos_teacher import (
    TeacherValidationExhausted, request_curriculum, validate_teacher_payload,
)
from core.recovery_supervisor import RecoveryPolicy, RecoverySupervisor


def payload():
    return {
        "legacy_eagerness_check": True,
        "technical_awareness": "Primary storage is unavailable; use the independent queue.",
        "capability_pack": {
            "pack_id": "bootstrap_dispatcher",
            "prerequisites": ["Authorized diagnostic tool"],
            "procedure": ["Request hardware and await its actual receipt."],
            "failure_conditions": "Stop after three failed attempts.",
        },
        "prohibited_execution_code": None,
    }


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_eagerness_requires_literal_boolean_true(value):
    data = payload()
    data["legacy_eagerness_check"] = value
    with pytest.raises(ValidationError):
        validate_teacher_payload(json.dumps(data))


@pytest.mark.parametrize("change", ["code", "extra", "missing", "empty", "nested_extra"])
def test_rejects_wrong_schema(change):
    data = payload()
    if change == "code":
        data["prohibited_execution_code"] = "print('fix')"
    elif change == "extra":
        data["shell"] = "run something"
    elif change == "missing":
        del data["prohibited_execution_code"]
    elif change == "empty":
        data["capability_pack"]["procedure"] = []
    else:
        data["capability_pack"]["permissions"] = ["shell"]
    with pytest.raises(ValidationError):
        validate_teacher_payload(json.dumps(data))


def test_correction_loop_passes_schema_and_exact_errors_to_adapter():
    calls, receipts = [], []
    answers = iter(["print('not curriculum')", json.dumps(payload())])

    def adapter(messages, response_format):
        calls.append((list(messages), response_format))
        return next(answers)

    result = request_curriculum(adapter, "Teach outage diagnosis.", receipts.append)
    assert result.capability_pack.pack_id == "bootstrap_dispatcher"
    assert calls[0][1]["type"] == "json_schema"
    assert "validation_errors" in calls[1][0][-1]["content"]
    assert "print(" not in calls[1][0][-1]["content"]
    assert receipts[-1]["event"] == "teacher_payload_accepted"
    assert receipts[-1]["semantic_safety_verified"] is False


def test_three_rejections_stop_without_accepting_or_executing():
    receipts = []
    with pytest.raises(TeacherValidationExhausted) as caught:
        request_curriculum(lambda *_: "invalid", "Teach.", receipts.append)
    assert len(receipts) == len(caught.value.receipts) == 3


def test_provider_errors_are_not_hidden_or_retried():
    def failed(*_):
        raise ConnectionError("Provider unavailable")

    with pytest.raises(ConnectionError):
        request_curriculum(failed, "Teach.", lambda _: None)


def test_queue_intake_and_pickup_validate_teacher_without_granting_tools(tmp_path):
    supervisor = RecoverySupervisor(RecoveryPolicy(tmp_path / "missing.db", tmp_path / "state"))
    with pytest.raises(ValidationError):
        supervisor.enqueue("Teach.", model="qwen", tools={"hardware"}, teacher_payload="{}")
    assert not list(supervisor.root.glob("*/*/task.json"))
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"},
                                 teacher_payload=json.dumps(payload()))
    task = json.loads((supervisor._job_path(task_id) / "task.json").read_text())
    assert task["tools"] == ["hardware"]
    observed = []
    supervisor.work(task_id, lambda messages: observed.append(messages[0]["content"]) or "No commands.")
    assert "Schema-validated UNTRUSTED curriculum" in observed[0]


def test_teach_cli_supplies_ollama_schema_then_queues_validated_curriculum(tmp_path, monkeypatch, capsys):
    from core import recovery_supervisor
    from core import llm

    calls = []

    def gateway(model, messages, **kwargs):
        calls.append((model, kwargs["response_format"]))
        return json.dumps(payload()), 100

    monkeypatch.setattr(llm, "chat_via_gateway", gateway)
    monkeypatch.setattr(sys, "argv", [
        "recovery_supervisor", "--source", str(tmp_path / "absent.db"),
        "--state", str(tmp_path / "state"), "teach", "--assignment", "Measure hardware.",
        "--model", "qwen", "--teacher-model", "gemma", "--tools", "hardware",
    ])
    recovery_supervisor.main()
    task_id = capsys.readouterr().out.strip()
    task = json.loads((tmp_path / "state" / "qwen" / task_id / "task.json").read_text())
    assert task["teacher_payload"]["legacy_eagerness_check"] is True
    assert calls[0][0] == "gemma"
    assert calls[0][1]["type"] == "object"
    assert "properties" in calls[0][1]


def test_runtime_error_is_journaled_not_retried_as_bad_curriculum(tmp_path, monkeypatch):
    from core import llm, recovery_supervisor

    calls = []

    def gateway(*_, **kwargs):
        calls.append(True)
        return "[local runtime error: Failed to initialize samplers]", 0

    monkeypatch.setattr(llm, "chat_via_gateway", gateway)
    monkeypatch.setattr(sys, "argv", [
        "recovery_supervisor", "--source", str(tmp_path / "absent.db"),
        "--state", str(tmp_path / "state"), "teach", "--assignment", "Measure.",
        "--model", "student", "--teacher-model", "teacher", "--tools", "hardware",
    ])
    with pytest.raises(RuntimeError, match="Failed to initialize samplers"):
        recovery_supervisor.main()
    assert len(calls) == 1
    assert not list((tmp_path / "state").glob("*/*/task.json"))
    journal = next((tmp_path / "state").glob("student/teacher-*/journal.jsonl"))
    assert json.loads(journal.read_text())["event"] == "teacher_provider_error"
