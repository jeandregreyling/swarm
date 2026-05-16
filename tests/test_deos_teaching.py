from utils import deos_teaching
from utils import watchdog_deos
import sqlite3


def test_local_agent_packet_contains_deos_contract_and_role_hint():
    packet = deos_teaching.local_agent_packet("mistral")

    assert "DEOS = Decides, Executes, Operates, Sustains" in packet
    assert "You own exactly one claimed task packet" in packet
    assert "DEOS_STATUS: done | blocked | needs_human" in packet
    assert "tiny bounded tasks" in packet


def test_watchdog_work_prompt_teaches_local_agent_contract():
    prompt = watchdog_deos._agent_work_prompt({
        "project_id": "P",
        "step_id": "S",
        "title": "Teach worker",
        "description": "Patch and prove.",
        "owner": "gemma",
        "owner_route": "watchdog:test",
    })

    assert "DEOS LOCAL WORKER CONTRACT" in prompt
    assert "code review" in prompt
    assert "Patch and prove." in prompt
    assert "DEOS_STATUS: done | blocked | needs_human" in prompt


def test_micro_task_prompt_preserves_exact_output_and_proof_guidance():
    prompt = watchdog_deos._compact_micro_task_prompt(
        "header\nDEOS_MICRO_TASK\nTask: Return exactly: Proof: READY"
    )

    assert "Preserve exact requested text and visible proof phrases" in prompt
    assert "Task: Return exactly: Proof: READY" in prompt


def test_deos_teaching_seed_steps_are_project_ready():
    steps = deos_teaching.studio_seed_steps("P-X")
    markdown = deos_teaching.format_seed_markdown(steps)

    assert [step["project_id"] for step in steps] == ["P-X", "P-X", "P-X"]
    assert all(step["step_id"].startswith("S-DEOS-") for step in steps)
    assert "House agent coaching loop" in markdown


def test_drill_queue_steps_create_relay_chain():
    steps = deos_teaching.drill_queue_steps("P-X", count=5, start_index=4, agents=["gemma", "llama", "mistral"])

    assert [step["step_id"] for step in steps] == [
        "S-DEOS-TEACHING-DRILL-04",
        "S-DEOS-TEACHING-DRILL-05",
        "S-DEOS-TEACHING-DRILL-06",
        "S-DEOS-TEACHING-DRILL-07",
        "S-DEOS-TEACHING-DRILL-08",
    ]
    assert [step["owner"] for step in steps] == ["gemma", "llama", "mistral", "gemma", "llama"]
    assert "Handoff: watchdog -> gemma -> llama" in steps[0]["description"]
    assert "Task: Return exactly: Proof: GEMMA_DEOS_DRILL_04_READY" in steps[0]["description"]
    assert steps[1]["owner_route"] == "watchdog:drill-queue:gemma->llama->mistral"


def test_local_result_evaluator_tracks_proof_and_status():
    review = deos_teaching.evaluate_local_result("Proof: pytest passed\nDEOS_STATUS: done")

    assert review["passed"] is True
    assert review["coaching_status"] == "passed"
    assert review["status"] == "done"
    assert review["issues"] == []


def test_local_result_evaluator_flags_missing_proof_without_hiding_output():
    review = deos_teaching.evaluate_local_result("Fixed it.\nDEOS_STATUS: done")

    assert review["passed"] is True
    assert review["coaching_status"] == "needs_coaching"
    assert review["issues"] == ["missing_proof"]
    assert review["visible"] == "Fixed it."


def test_local_result_evaluator_blocks_refusals_and_missing_status():
    refusal = deos_teaching.evaluate_local_result("I'm sorry, I am unable to assist.\nDEOS_STATUS: done")
    missing = deos_teaching.evaluate_local_result("I looked at it but did not prove it.")

    assert refusal["passed"] is False
    assert "refusal" in refusal["issues"]
    assert missing["status"] == ""
    assert "missing_deos_status" in missing["issues"]


def test_watchdog_deos_evidence_write_retries_sqlite_locks(monkeypatch):
    calls = []
    sleeps = []

    class Conn:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            if len(calls) < 3:
                raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(watchdog_deos.time, "sleep", lambda seconds: sleeps.append(seconds))

    watchdog_deos._add_step_evidence(Conn(), "S", "ref", "summary")

    assert len(calls) == 3
    assert sleeps == [0.25, 0.5]
