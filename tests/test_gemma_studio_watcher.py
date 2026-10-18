from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    from utils.db import _connection as conn_mod

    db_path = tmp_path / "gemma-studio.db"
    monkeypatch.setenv("SWARM_DB_PATH", str(db_path))
    monkeypatch.setattr(conn_mod, "DB_PATH", str(db_path), raising=False)

    import core.knowledge.projects as pj
    import core.knowledge.test_runs as tr

    monkeypatch.setattr(pj, "_SCHEMA_READY", False, raising=False)
    monkeypatch.setattr(tr, "_SCHEMA_READY", False, raising=False)
    yield db_path


def test_watch_studio_processes_step_and_writes_quintum_notes(isolated_db, monkeypatch):
    from agents.gemma import gemma_agent
    from core.knowledge import projects as pj

    pid = pj.create_project("Quintum worker", description="Project level context for Gemma.")
    sid = pj.add_step(
        pid,
        "Draft a rollout note",
        description="Summarise the required rollout steps. Mention validation and monitoring."
    )

    monkeypatch.setattr(gemma_agent, "_ollama_available", lambda: True)
    monkeypatch.setattr(
        gemma_agent,
        "_probe_chunk",
        lambda chunk, step_title: f"finding for {step_title}: {chunk[:24]}",
    )
    monkeypatch.setattr(
        gemma_agent,
        "_synthesise",
        lambda notes, step_title: f"synthesis for {step_title} with {len(notes)} notes",
    )
    monkeypatch.setattr(gemma_agent, "_validate", lambda synthesis, step_title, step_description="": True)

    results = gemma_agent.watch_studio(max_steps=1)

    assert results == [{"step_id": sid, "status": "done", "retries": 0}]
    step = pj.get_step(sid)
    assert step["status"] == "done"
    assert step["owner"] == "fred"

    notes = pj.list_blackboard_notes(pid, status=None)
    assert any(note["kind"] == "quintum-chunk" for note in notes)
    assert any(note["kind"] == "quintum-synthesis" for note in notes)


def test_watch_studio_marks_oversized_steps_for_bigger_model(isolated_db, monkeypatch):
    from agents.gemma import gemma_agent
    from core.knowledge import projects as pj

    pid = pj.create_project("Oversized project")
    sid = pj.add_step(pid, "Huge step", description="A" * 4000)

    monkeypatch.setattr(gemma_agent, "_ollama_available", lambda: True)
    monkeypatch.setattr(gemma_agent, "_MAX_INPUT_TOKENS", 10)

    results = gemma_agent.watch_studio(max_steps=1)

    assert results == [{"step_id": sid, "status": "skip-too-large", "retries": 0}]
    step = pj.get_step(sid)
    assert step["status"] == "todo"
    assert step["owner"] == "skip-too-large"


def test_setup_studio_watcher_task_uses_one_minute_interval(monkeypatch):
    import fridays.scheduler as scheduler

    captured = {}

    def fake_add_task(**kwargs):
        captured.update(kwargs)
        return 41

    monkeypatch.setattr(scheduler, "add_task", fake_add_task)

    assert scheduler.setup_studio_watcher_task() == 41
    assert captured["name"] == "studio_watcher"
    assert captured["schedule"] == "interval 1m"
    assert captured["action_type"] == "PYTHON"
    assert captured["action_data"] == "studio_watcher 3"
