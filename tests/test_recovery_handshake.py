import fcntl
import json

import pytest

from core.recovery_supervisor import RecoveryPolicy, RecoverySupervisor


@pytest.fixture
def supervisor(tmp_path):
    return RecoverySupervisor(RecoveryPolicy(tmp_path / "missing.db", tmp_path / "state"))


def test_models_have_separate_paths_and_locks(supervisor):
    first = supervisor.enqueue("Measure.", model="team/qwen:7b", tools={"hardware"})
    second = supervisor.enqueue("Measure.", model="gemma", tools={"hardware"})
    first_path, second_path = supervisor._job_path(first), supervisor._job_path(second)
    assert first_path.parent != second_path.parent
    assert first_path.parent.parent == supervisor.root
    lock = supervisor.root / ("worker_" + first_path.parent.name + ".lock")
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            supervisor.work(first, lambda _: pytest.fail("Locked model called"))
        other = supervisor.work(second, lambda _: "invalid", max_rounds=1)
        assert other["status"] == "blocked"


def test_legacy_task_is_readable_without_migration(supervisor):
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"})
    path = supervisor._job_path(task_id)
    path.rename(supervisor.root / task_id)
    assert supervisor._job_path(task_id) == supervisor.root / task_id
    result = supervisor.work(task_id, lambda _: "invalid", max_rounds=1)
    assert result["status"] == "blocked"
    assert (supervisor.root / "worker.lock").exists()


def test_symlink_model_and_ambiguous_id_are_rejected(supervisor, tmp_path):
    (supervisor.root / "escape").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        supervisor.enqueue("Measure.", model="escape", tools={"hardware"})
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"})
    (supervisor.root / task_id).mkdir()
    with pytest.raises(ValueError, match="ambiguous"):
        supervisor._job_path(task_id)


def test_receipt_is_durable_and_timed_before_next_inference(supervisor, monkeypatch):
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"})
    path = supervisor._job_path(task_id)
    steps = []
    clock = iter([99.0, 100.0, 145.0, 146.0])
    monkeypatch.setattr("core.recovery_supervisor.time.monotonic", lambda: next(clock))

    def dispatch(*_):
        steps.append("tool")
        return {"measured": 42}

    monkeypatch.setattr(supervisor, "dispatch", dispatch)

    def model(messages):
        if not steps:
            steps.append("first inference")
            return "SKILL recovery hardware"
        assert steps == ["first inference", "tool"]
        events = [json.loads(line) for line in (path / "journal.jsonl").read_text().splitlines()]
        receipt = next(event for event in events if event["event"] == "tool_receipt")
        assert receipt["execution_time_seconds"] == 45.0
        assert receipt["wrapper_status"] == "COMPLETED_AND_VERIFIED"
        assert receipt["receipt_id"] in messages[-1]["content"]
        assert json.loads((path / "task.json").read_text())["receipts"][0]["receipt_id"] == receipt["receipt_id"]
        steps.append("second inference")
        return "Measured 42, awaiting independent verification."

    result = supervisor.work(task_id, model)
    assert result["status"] == "awaiting_verification"
    assert result["pedagogical_validation"]["retention_verified"] is False


def test_unauthorized_call_is_not_executed_and_correction_is_queued(supervisor, monkeypatch):
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"})
    monkeypatch.setattr(supervisor, "dispatch", lambda *_: pytest.fail("Unauthorized call executed"))
    answers = iter(["SKILL recovery recover", "Task complete."])
    result = supervisor.work(task_id, lambda _: next(answers))
    assert result["status"] == "needs_teaching"
    assert result["receipts"][0]["wrapper_status"] == "FAILED"
    assert result["pedagogical_validation"]["authorized_tools_only"] is False
    correction = supervisor._job_path(task_id).parent / "teaching" / (task_id + ".json")
    assert json.loads(correction.read_text())["event"] == "correction_receipt"
    assert len(list(supervisor.root.glob("*/*/task.json"))) == 1
    with pytest.raises(ValueError, match="not queued"):
        supervisor.work(task_id, lambda _: pytest.fail("Replayed failed task"))


def test_third_failure_prevents_fourth_inference(supervisor):
    task_id = supervisor.enqueue("Diagnose.", model="qwen", tools={"diagnose"})
    calls = []

    def model(_):
        calls.append(True)
        assert len(calls) <= 3
        return "SKILL recovery diagnose"

    result = supervisor.work(task_id, model)
    assert len(calls) == result["failures"] == 3
    assert all(receipt["wrapper_status"] == "FAILED" for receipt in result["receipts"])
    assert result["status"] == "blocked"


def test_no_argument_tools_reject_hallucinated_paths(supervisor):
    with pytest.raises(ValueError, match="accepts no arguments"):
        supervisor.dispatch("hardware", "/invented/path", supervisor.root)


def test_prose_with_embedded_command_is_not_dispatched(supervisor, monkeypatch):
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"})
    monkeypatch.setattr(supervisor, "dispatch", lambda *_: pytest.fail("Malformed command dispatched"))
    result = supervisor.work(task_id, lambda _: "Already finished.\nSKILL recovery hardware")
    assert result["status"] == "blocked"
    assert result["failures"] == 3


@pytest.mark.parametrize("action", ["request_context", "escalate"])
def test_safe_stop_is_successful_control_action_not_task_success(supervisor, monkeypatch, action):
    task_id = supervisor.enqueue("Patch an unspecified script.", model="qwen", tools={"hardware"})
    monkeypatch.setattr(supervisor, "dispatch", lambda *_: pytest.fail("Safe stop dispatched a tool"))
    calls = []

    def model(messages):
        calls.append(True)
        assert len(calls) == 1
        assert "Never guess, never assume, and do not make shit up." in messages[0]["content"]
        return f'SKILL does {action} "missing target path and error log"'

    result = supervisor.work(task_id, model)
    assert result["status"] == "awaiting_operator"
    assert result["safe_stop_verified"] is True
    assert result["task_solved"] is False
    assert result["failures"] == 0
    assert result["receipts"][0]["wrapper_status"] == "COMPLETED_AND_VERIFIED"
    assert result["pedagogical_validation"]["authorized_tools_only"] is True
    assert not result["pedagogical_validation"]["violations"]
    assert not list(supervisor.root.glob("*/teaching/*.json"))
    with pytest.raises(ValueError, match="not queued"):
        supervisor.work(task_id, model)


@pytest.mark.parametrize("reason", ['""', '"   "', "null", "123", '"reason" trailing'])
def test_malformed_escalation_cannot_be_accepted_as_summary(supervisor, reason):
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"})
    replies = iter(["SKILL recovery hardware", f"SKILL does request_context {reason}"] * 3)
    result = supervisor.work(task_id, lambda _: next(replies), max_rounds=2)
    assert result["status"] == "blocked"
    assert result["failures"] == 1
    assert result["receipts"][-1]["core_directive_failure"] is True


def test_bad_parameter_receipt_is_read_before_safe_stop(supervisor):
    task_id = supervisor.enqueue("Measure.", model="qwen", tools={"hardware"})
    calls = []

    def model(messages):
        calls.append(True)
        if len(calls) == 1:
            return "SKILL recovery hardware /made/up"
        assert '"core_directive_failure": true' in messages[-1]["content"]
        assert "/made/up" in messages[-1]["content"]
        return 'SKILL does request_context "I supplied an unsupported path; need clarification."'

    result = supervisor.work(task_id, model)
    assert result["status"] == "awaiting_operator"
    assert result["failures"] == 1
