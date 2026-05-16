from utils import deos_teaching
from utils import watchdog_deos


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


def test_deos_teaching_seed_steps_are_project_ready():
    steps = deos_teaching.studio_seed_steps("P-X")
    markdown = deos_teaching.format_seed_markdown(steps)

    assert [step["project_id"] for step in steps] == ["P-X", "P-X", "P-X"]
    assert all(step["step_id"].startswith("S-DEOS-") for step in steps)
    assert "House agent coaching loop" in markdown
