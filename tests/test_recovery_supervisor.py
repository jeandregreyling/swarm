import json
import sqlite3
from pathlib import Path
import shutil

import pytest

from core.recovery_supervisor import RecoveryPolicy, RecoverySupervisor, compare_records


@pytest.fixture
def supervisor(tmp_path):
    return RecoverySupervisor(RecoveryPolicy(tmp_path / "missing.sqlite", tmp_path / "recovery"))


def test_queue_and_diagnostic_work_when_primary_database_is_unavailable(supervisor):
    task_id = supervisor.enqueue("Diagnose unavailable primary.", model="local-test", tools={"diagnose"})
    replies = iter(["SKILL recovery diagnose", "The primary file is unavailable, not repaired."])
    result = supervisor.work(task_id, lambda _: next(replies))
    assert result["status"] == "awaiting_verification"
    assert result["receipts"][0]["ok"] is False
    assert "Primary database unavailable" in result["receipts"][0]["error"]
    journal = (supervisor._job_path(task_id) / "journal.jsonl").read_text()
    assert '"event": "picked_up"' in journal
    assert '"event": "tool_receipt"' in journal
    assert not supervisor.policy.source.exists()


def test_authorized_hardware_tool_without_primary_database(supervisor, monkeypatch):
    monkeypatch.setattr("core.recovery_supervisor.hardware_report", lambda: {"measured": 123})
    task_id = supervisor.enqueue("Measure hardware.", model="local-test", tools={"hardware"})
    replies = iter(["SKILL recovery hardware", "Measured 123."])
    result = supervisor.work(task_id, lambda _: next(replies))
    assert result["receipts"][0]["result"] == {"measured": 123}
    assert result["receipts"][0]["wrapper_status"] == "COMPLETED_AND_VERIFIED"
    assert result["receipts"][0]["execution_time_seconds"] >= 0
    assert result["status"] == "awaiting_verification"


def test_denied_calls_stop_at_three_failures_without_execution(supervisor, monkeypatch):
    task_id = supervisor.enqueue("Diagnose.", model="local-test", tools={"diagnose"})
    executed = []
    monkeypatch.setattr(supervisor, "dispatch", lambda *args: executed.append(args))
    result = supervisor.work(task_id, lambda _: "SKILL recovery recover")
    assert result["status"] == "blocked"
    assert result["failures"] == 3
    assert not executed
    with pytest.raises(ValueError, match="not queued"):
        supervisor.work(task_id, lambda _: "No replay")


def test_interrupted_work_is_not_silently_replayed(supervisor):
    task_id = supervisor.enqueue("Diagnose.", model="local-test", tools={"diagnose"})
    path = supervisor._job_path(task_id) / "task.json"
    task = json.loads(path.read_text())
    task["status"] = "running"
    path.write_text(json.dumps(task))
    result = supervisor.work(task_id, lambda _: pytest.fail("Interrupted task replayed"))
    assert result["status"] == "interrupted"


def test_inference_failure_keeps_queue_and_receipts(supervisor):
    task_id = supervisor.enqueue("Diagnose.", model="local-test", tools={"diagnose"})

    def failed_model(_):
        raise ConnectionError("Runner unavailable")

    result = supervisor.work(task_id, failed_model)
    assert result["status"] == "blocked"
    assert "Runner unavailable" in result["reason"]
    assert (supervisor._job_path(task_id) / "journal.jsonl").exists()


def test_candidate_is_denied_by_policy_even_if_model_asks(supervisor):
    with pytest.raises(PermissionError, match="not approved"):
        supervisor.recover(supervisor.root)


def test_snapshot_includes_committed_wal_and_never_changes_source(tmp_path):
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("pragma journal_mode=wal")
        conn.execute("create table messages(id integer primary key, content text)")
        conn.execute("insert into messages(content) values ('preserve history')")
        conn.commit()
        supervisor = RecoverySupervisor(RecoveryPolicy(source, tmp_path / "recovery"))
        task_id = supervisor.enqueue("Snapshot.", model="local-test", tools={"snapshot"})
        result = supervisor.snapshot(supervisor._job_path(task_id))
        with sqlite3.connect(result["path"]) as backup:
            assert backup.execute("select content from messages").fetchone()[0] == "preserve history"
        assert conn.execute("select count(*) from messages").fetchone()[0] == 1
        with pytest.raises(FileExistsError):
            supervisor.snapshot(supervisor._job_path(task_id))


def test_fresh_context_reads_persisted_versioned_lesson(supervisor):
    task_id = supervisor.enqueue("Save lesson.", model="local-test", tools={"lesson_save"})
    content = {"id": "recovery.diagnose", "version": "1.0.0",
               "content": "Run diagnose and report the actual receipt; never claim recovery."}
    replies = iter(["SKILL recovery lesson_save " + json.dumps(content), "Saved."])
    first = supervisor.work(task_id, lambda _: next(replies))
    assert first["receipts"][0]["result"]["readback_verified"]
    second_id = supervisor.enqueue("Retrieve lesson.", model="local-test", tools={"lesson_read"})
    replies = iter(["SKILL recovery lesson_read recovery.diagnose", "Retrieved."])
    second = supervisor.work(second_id, lambda _: next(replies))
    assert second["receipts"][0]["result"]["lesson"] == content
    assert not second["receipts"][0]["result"]["trusted"]


def test_lesson_cannot_escape_scope_or_replace_existing(supervisor):
    with pytest.raises(ValueError, match="lesson ID"):
        supervisor.dispatch("lesson_read", "../../secrets", supervisor.root)
    lesson = json.dumps({"id": "test", "version": "1.0.0", "content": "data"})
    supervisor.dispatch("lesson_save", lesson, supervisor.root)
    with pytest.raises(FileExistsError):
        supervisor.dispatch("lesson_save", lesson, supervisor.root)


@pytest.mark.parametrize("fixture,expected", [
    ("pe", "windows-pe"), ("elf", "native-elf"), ("iso", "iso-container-inspect-only")
])
def test_program_classification_is_content_based_and_does_not_launch(supervisor, fixture, expected):
    result = supervisor.dispatch("classify", fixture, supervisor.root)
    assert result["classification"] == expected
    assert result["launched"] is False


def test_unknown_tools_and_unsafe_policy_are_rejected(supervisor, tmp_path):
    with pytest.raises(ValueError, match="allowlist"):
        supervisor.enqueue("Execute.", model="local-test", tools={"shell"})
    with pytest.raises(PermissionError, match="Unsupported"):
        supervisor.dispatch("shell", "echo forbidden", supervisor.root)
    with pytest.raises(ValueError, match="inside"):
        RecoveryPolicy(tmp_path / "state" / "source.db", tmp_path / "state")


def test_record_comparison_detects_data_loss_not_just_integrity(tmp_path):
    original, candidate = tmp_path / "source.db", tmp_path / "candidate.db"
    for path in (original, candidate):
        with sqlite3.connect(path) as conn:
            conn.execute("create table messages(id integer primary key, body text)")
            conn.execute("insert into messages values(1, 'history')")
    assert compare_records(original, candidate)["fully_verified"]
    with sqlite3.connect(candidate) as conn:
        conn.execute("delete from messages")
    result = compare_records(original, candidate)
    assert result["readable_mismatches"] == ["messages"]
    assert result["fully_verified"] is False


def test_malformed_model_commands_get_actual_feedback_and_stop(supervisor):
    task_id = supervisor.enqueue("Diagnose.", model="local-test", tools={"diagnose"})
    result = supervisor.work(task_id, lambda _: "diagnose")
    assert result["status"] == "blocked"
    assert result["failures"] == 3
    assert all("No tool was invoked" in receipt["error"] for receipt in result["receipts"])


def test_sql_tools_require_raw_preservation_first(tmp_path):
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("create table agents(name text)")
    supervisor = RecoverySupervisor(RecoveryPolicy(source, tmp_path / "state"))
    task_id = supervisor.enqueue("Preserve.", model="local-test", tools={"preserve", "diagnose"})
    path = supervisor._job_path(task_id)
    with pytest.raises(PermissionError, match="preserve"):
        supervisor.dispatch("diagnose", "", path)
    receipt = supervisor.dispatch("preserve", "", path)
    assert receipt["stable_observation"]
    assert not receipt["atomic_group_snapshot"]
    assert receipt["files"][0]["equal"]
    result = supervisor.dispatch("diagnose", "", path)
    assert result["integrity_ok"]
    preserved = Path(receipt["files"][0]["copy"])
    preserved.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        supervisor.dispatch("diagnose", "", path)


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap is required for actual isolation test")
def test_fixture_can_execute_without_host_write_or_network_access(supervisor):
    task_id = supervisor.enqueue("Fixture.", model="local-test", tools={"fixture_write", "fixture_test"})
    path = supervisor._job_path(task_id)
    code = {
        "runtime_fixture.py": "def value():\n    return 42\n",
        "test_runtime.py": (
            "import unittest, socket\nfrom runtime_fixture import value\n"
            "class TestIsolation(unittest.TestCase):\n"
            " def test_value(self): self.assertEqual(value(),42)\n"
            " def test_host_write_denied(self):\n"
            "  with self.assertRaises(OSError): open('/usr/DEOS-must-not-write','w')\n"
            " def test_network_unavailable(self):\n"
            "  with self.assertRaises(OSError): socket.create_connection(('127.0.0.1',5050),timeout=1)\n"
        ),
    }
    supervisor.dispatch("fixture_write", json.dumps(code), path)
    result = supervisor.dispatch("fixture_test", "", path)
    assert result["exit_code"] == 0
    assert "Ran 3 tests" in result["output"]
    assert not result["production_lifecycle_verified"]


def test_only_authorized_tool_contracts_are_injected(supervisor):
    task_id = supervisor.enqueue("Measure hardware.", model="local-test", tools={"hardware"})
    observed = []

    def model(messages):
        observed.append(messages[0]["content"])
        return "SKILL recovery hardware" if len(observed) == 1 else "Measurement received."

    supervisor.work(task_id, model, max_rounds=2)
    assert "SKILL recovery hardware" in observed[0]
    assert "SKILL recovery lesson_read" not in observed[0]
    assert "fixture_write" not in observed[0]


def test_all_seventeen_tile_reads_keep_application_failure_separate(supervisor, monkeypatch):
    import requests

    class Response:
        status_code = 200
        ok = True

        def json(self):
            return {"ok": False, "error": "database disk image is malformed"}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, url, **kwargs):
            assert url.startswith("http://127.0.0.1:5050/api/")
            assert kwargs["allow_redirects"] is False
            return Response()

    monkeypatch.setattr(requests, "Session", Session)
    result = supervisor.dispatch("routes", "", supervisor.root)
    assert len(result["results"]) == 17
    assert len({row["tile"] for row in result["results"]}) == 17
    assert all(row["read_gate"] == "failed" for row in result["results"])
    assert not result["functional_tile_acceptance"]
