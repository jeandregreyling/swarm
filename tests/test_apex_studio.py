import json
import sqlite3

import pytest

from core import apex_studio
from core.apex_tools import run_apex_tools


@pytest.fixture
def studio(tmp_path, monkeypatch):
    path = tmp_path / "studio.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.executescript("""
            CREATE TABLE projects(project_id TEXT PRIMARY KEY,name TEXT,description TEXT,
                methodology TEXT,status TEXT,owner TEXT,created_at REAL,updated_at REAL,tags TEXT);
            CREATE TABLE project_steps(step_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,
                description TEXT,status TEXT,owner TEXT,order_idx INTEGER,created_at REAL,updated_at REAL);
            CREATE TABLE project_blackboard_notes(note_id TEXT PRIMARY KEY,project_id TEXT,author TEXT,
                kind TEXT,content TEXT,status TEXT,created_at REAL,updated_at REAL);
        """)
    monkeypatch.setattr(apex_studio, "get_connection", connect)
    monkeypatch.setattr(apex_studio.projects, "_ensure_schema", lambda: None)
    return connect


def save(**kwargs):
    values = dict(title="Hummingbird ingestion", summary="No write approved",
                  tasks=["Propose script", "Review approval"], context=[], receipts=[])
    values.update(kwargs)
    return apex_studio.save_handoff(2826, "operator", "Continue ingestion", **values)


def test_handoff_preserves_full_context_and_reopens_in_small_pages(studio):
    original = "Full operator requirement\n" * 1500
    receipt = {"id": "receipt-1", "tool": "propose_patch", "status": "denied", "output": "not a fact"}
    result = save(context=[{"role": "user", "content": original}], receipts=[receipt])
    assert result["context_parts"] > 1
    pages, offset = [], 0
    while True:
        page = apex_studio.read_handoff(2826, "operator", offset=offset)
        assert page["project"]["status"] == "on_hold"
        assert len(page["tasks"]) == 2 and len(page["context"]) <= 1500
        pages.append(page["context"])
        offset = page["next_offset"]
        if offset is None:
            break
    restored = json.loads("".join(pages))
    assert restored["operator_context"] == [original]
    assert restored["receipt_handles"] == [{"id": "receipt-1", "tool": "propose_patch", "status": "denied"}]
    assert restored["boundary"].startswith("No mutation is approved")
    with studio() as conn:
        assert {row["owner"] for row in conn.execute("SELECT owner FROM project_steps")} == {"apex"}


def test_handoff_is_idempotent_and_reads_only_latest_snapshot(studio):
    first = save(context=[{"role": "user", "content": "First context"}])
    assert save(context=[{"role": "user", "content": "First context"}]) == first
    with studio() as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM project_steps").fetchone()[0] == 2
    second = save(tasks=["Next task"], context=[{"role": "user", "content": "New context"}])
    assert second["project_id"] == first["project_id"]
    page = apex_studio.read_handoff(2826, "operator")
    assert [task["title"] for task in page["tasks"]] == ["Next task"]
    assert "First context" in page["context"] and "New context" in page["context"]


def test_handoff_read_is_operator_and_conversation_scoped(studio):
    save()
    for conversation, owner in [(2827, "operator"), (2826, "another")]:
        with pytest.raises(ValueError, match="No Studio handoff"):
            apex_studio.read_handoff(conversation, owner)
    with pytest.raises(PermissionError):
        apex_studio.read_handoff(2826, "")


def test_handoff_failure_rolls_back_project_context_and_steps(studio):
    with studio() as conn:
        conn.execute("CREATE TRIGGER reject_steps BEFORE INSERT ON project_steps "
                     "BEGIN SELECT RAISE(ABORT, 'storage failure'); END")
    with pytest.raises(sqlite3.DatabaseError, match="storage failure"):
        save()
    with studio() as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM project_blackboard_notes").fetchone()[0] == 0


def test_handoff_missing_or_corrupt_part_never_returns_success(studio):
    save(context=[{"role": "user", "content": "x" * 10000}])
    with studio() as conn:
        conn.execute("DELETE FROM project_blackboard_notes WHERE content LIKE '%part 2/%'")
    with pytest.raises(RuntimeError, match="parts are missing"):
        apex_studio.read_handoff(2826, "operator")


def test_live_task_board_is_scoped_and_keeps_previous_tasks(studio):
    save()
    latest = save(tasks=["Verify live chat"])
    board = apex_studio.read_task_board(2826, "operator")
    assert board["snapshot_sha256"] == latest["snapshot_sha256"]
    assert board["total"] == 3
    assert {t["status"] for t in board["tasks"]} == {"todo", "skipped"}
    assert "context" not in board and "receipts" not in board
    for conversation, owner in [(2827, "operator"), (2826, "another")]:
        other = apex_studio.read_task_board(conversation, owner)
        assert other["project"] is None and other["tasks"] == []


def test_live_task_board_pages_reject_mixed_revisions(studio):
    saved = save()
    with studio() as conn:
        for i in range(25):
            conn.execute(
                "INSERT INTO project_steps VALUES (?,?,?,?,?,?,?,?,?)",
                (f"EXTRA-{i}", saved["project_id"], f"Task {i}", "", "todo",
                 "copilot-instructor", i + 2, 1, 1),
            )
    first = apex_studio.read_task_board(2826, "operator")
    assert len(first["tasks"]) == 20 and first["total"] == 27
    second = apex_studio.read_task_board(
        2826, "operator", offset=first["next_offset"], revision=first["revision"])
    assert len(second["tasks"]) == 7 and second["next_offset"] is None
    assert not ({t["step_id"] for t in first["tasks"]} & {t["step_id"] for t in second["tasks"]})
    with studio() as conn:
        conn.execute("UPDATE project_steps SET status='doing',updated_at=9999999999 WHERE step_id='EXTRA-0'")
    with pytest.raises(ValueError, match="changed"):
        apex_studio.read_task_board(2826, "operator", offset=20, revision=first["revision"])
    updated = apex_studio.read_task_board(2826, "operator")
    assert updated["tasks"][0]["step_id"] == "EXTRA-0"
    assert updated["tasks"][0]["status"] == "doing"


def test_live_task_board_does_not_hide_snapshot_corruption(studio):
    save(context=[{"role": "user", "content": "x" * 10000}])
    with studio() as conn:
        conn.execute("DELETE FROM project_blackboard_notes WHERE content LIKE '%part 2/%'")
    with pytest.raises(RuntimeError, match="parts are missing"):
        apex_studio.read_task_board(2826, "operator")


@pytest.mark.parametrize("override", [{"tasks": []}, {"tasks": ["one", "one"]},
                                      {"tasks": ["x" * 201]}, {"summary": ""}])
def test_handoff_rejects_invalid_tasks_before_writing(studio, override):
    with pytest.raises(ValueError):
        save(**override)


@pytest.mark.parametrize("reason", [
    "APEX context budget exceeded: protected input does not fit",
    "APEX output budget exhausted: finish_reason=length",
])
def test_capacity_failure_saves_handoff_instead_of_crashing(reason):
    received, receipts = [], []

    def model(*_):
        raise RuntimeError(reason)

    def handler(tool, args):
        received.append((tool, args))
        return {"project_id": "P-TEST", "state": "handoff"}

    answer, _, results = run_apex_tools(model, [{"role": "user", "content": "Write code"}],
                                       lambda: True, receipts.append, studio_handler=handler)
    assert "P-TEST" in answer and "this handoff grants no new approval" in answer
    assert "Existing receipt statuses remain authoritative" in answer
    assert received[0][0] == "studio_capacity_handoff"
    assert len(receipts) == 1 and receipts == results
    assert receipts[0]["status"] == "succeeded"


def test_explicit_studio_handoff_stops_inference_after_real_receipt():
    calls, receipts = [], []

    def model(*_):
        calls.append(1)
        return json.dumps({"tool_calls": [{"name": "studio_handoff", "arguments": {
            "title": "Task", "summary": "Need another window", "tasks": ["Next task"]}}], "answer": ""}), 10

    answer, _, _ = run_apex_tools(model, [{"role": "user", "content": "Use Studio"}],
                                 lambda: True, receipts.append,
                                 studio_handler=lambda *_: {"project_id": "P-SAVED"},
                                 prepare_receipts=lambda *_: pytest.fail("Terminal handoff needs no next prompt"))
    assert len(calls) == 1 and receipts[0]["status"] == "succeeded"
    assert "P-SAVED" in answer
    assert "Existing receipt statuses remain authoritative" in answer
    assert "this handoff grants no new approval" in answer


def test_no_studio_handler_or_permission_cannot_write_on_capacity_failure():
    def model(*_):
        raise RuntimeError("APEX output budget exhausted")

    for kwargs in [{}, {"studio_handler": lambda *_: pytest.fail("Unauthorized write")}]:
        with pytest.raises(RuntimeError, match="output budget exhausted"):
            run_apex_tools(model, [{"role": "user", "content": "Do not use tools"}],
                           lambda: False, lambda _: None, **kwargs)


def test_oversized_input_hands_off_without_inference_or_mutation():
    from core.apex_context import prepare_context, CONTEXT_TOKENS
    calls = []
    received = []

    def handler(tool, args):
        received.append((tool, args))
        return {"project_id": "P-INPUT"}

    answer, _, _ = run_apex_tools(
        lambda *_: pytest.fail("Oversized prompt submitted"),
        [{"role": "user", "content": "x" * CONTEXT_TOKENS}], lambda: True, calls.append,
        prepare_messages=lambda messages: prepare_context(
            messages, lambda current: sum(len(m["content"]) for m in current)),
        studio_handler=handler,
    )
    assert "P-INPUT" in answer and received[0][0] == "studio_capacity_handoff"
    assert calls[0]["status"] == "succeeded"


def test_automatic_capacity_pause_keeps_the_existing_concrete_task_plan(studio):
    first = save(tasks=["Propose script", "Await human approval", "Validate metadata"])
    next_result = save(summary="APEX context budget exceeded", tasks=["Generic next step"], preserve_tasks=True)
    assert next_result["project_id"] == first["project_id"]
    page = apex_studio.read_handoff(2826, "operator")
    assert [task["title"] for task in page["tasks"]] == [
        "Propose script", "Await human approval", "Validate metadata"]
    with studio() as conn:
        assert conn.execute("SELECT COUNT(*) FROM project_steps").fetchone()[0] == 3


def test_new_task_plan_keeps_completion_status_and_retires_superseded_tasks(studio):
    first = save(tasks=["Verified", "Old task"])
    with studio() as conn:
        conn.execute("UPDATE project_steps SET status='done' WHERE step_id=?", (first["step_ids"][0],))
    save(tasks=["Verified", "Next task"], context=[{"role": "user", "content": "New requirements"}])
    page = apex_studio.read_handoff(2826, "operator")
    assert [(task["title"], task["status"]) for task in page["tasks"]] == [
        ("Verified", "done"), ("Next task", "todo")]
    with studio() as conn:
        assert conn.execute("SELECT status FROM project_steps WHERE title='Old task'").fetchone()[0] == "skipped"


def test_wrapper_records_ordinary_turns_full_receipts_outputs_and_usage(studio):
    context = [{"role": "user", "content": "Operator request"},
               {"role": "assistant", "content": "Previous verified reply"}]
    receipt = {"id": "real", "tool": "git_status", "status": "succeeded", "output": " M probe.py"}
    first = apex_studio.record_turn(2826, "operator", "Inspect status", context, [], state="running")
    completed = apex_studio.record_turn(
        2826, "operator", "Inspect status", context, [receipt], state="completed",
        response="probe.py modified", tokens=42, telemetry=[{"prompt_tokens_after": 3100}])
    assert first["project_id"] == completed["project_id"]
    with studio() as conn:
        _, text = apex_studio._snapshot(conn, first["project_id"])
        saved = json.loads(text)
        assert saved["conversation_context"] == context
        assert saved["receipts"] == [receipt]
        assert saved["outcome"]["response"] == "probe.py modified"
        assert saved["outcome"]["completion_tokens"] == 42
        assert saved["outcome"]["context_telemetry"] == [{"prompt_tokens_after": 3100}]
        assert conn.execute("SELECT status FROM project_steps WHERE title='Inspect status'").fetchone()[0] == "partial"
    assert first["project_id"] in apex_studio.working_state(2826, "operator")


def test_repeated_malformed_payload_automatically_saves_without_dispatching():
    calls = []
    answer, _, receipts = run_apex_tools(
        lambda *_: ('{"tool_calls":[', 10),
        [{"role": "user", "content": "Propose a file"}], lambda: True, lambda _: None,
        studio_handler=lambda tool, args: calls.append(tool) or {"project_id": "P-FORMAT"},
    )
    assert calls == ["studio_capacity_handoff"]
    assert "P-FORMAT" in answer and "malformed" in answer
    assert [r["tool"] for r in receipts] == ["studio_handoff"]


def test_terminal_turn_writes_readable_trace_to_thread_and_linked_alm_project(studio):
    with studio() as conn:
        conn.execute("INSERT INTO projects(project_id,name,status,owner) VALUES ('P-ALM0000001','ALM','active','ghost')")
        conn.execute("INSERT INTO project_steps(step_id,project_id,title,status,owner) "
                     "VALUES ('S-ABCDEF0123','P-ALM0000001','T1','todo','apex')")
    receipts = [
        {"id": "r1", "tool": "alm_step_get", "arguments": {"step_id": "S-ABCDEF0123"},
         "status": "succeeded", "output": "x" * 2067},
        {"id": "r2", "tool": "grep_repo", "arguments": {"query": "q", "path": "tests"},
         "status": "failed", "output": "boom", "context_omitted": True},
    ]
    telemetry = [{"phase": "inference", "prompt_tokens_after": 3148, "input_budget": 5120, "compacted_messages": 0},
                 {"phase": "receipts", "prompt_tokens_after": 3300, "input_budget": 5120, "compacted_messages": 1},
                 {"phase": "inference", "prompt_tokens_after": 3400, "input_budget": 5120, "compacted_messages": 0,
                  "correction": "BACKEND STEP CHECK"}]
    running = apex_studio.record_turn(2826, "operator", "Work step", [], receipts, state="running")
    assert "trace_notes" not in running
    done = apex_studio.record_turn(2826, "operator", "Work step", [], receipts, state="blocked",
                                   response="Unable to retrieve", telemetry=telemetry, message_id=8996)
    assert set(done["trace_notes"]) == {done["project_id"], "P-ALM0000001"}
    with studio() as conn:
        rows = conn.execute("SELECT project_id, content FROM project_blackboard_notes "
                            "WHERE kind='trace' AND author='apex'").fetchall()
    assert len(rows) == 2 and rows[0]["content"] == rows[1]["content"]
    text = rows[0]["content"]
    assert "operator message 8996, state blocked" in text
    assert "Model rounds: 2; prompt tokens per round: 3148/5120, 3400/5120; context items archived: 1" in text
    assert "Backend corrections sent before: round 2 BACKEND STEP CHECK" in text
    assert '1. alm_step_get {"step_id": "S-ABCDEF0123"} -> succeeded (receipt r1, 2067 chars)' in text
    assert "2. grep_repo" in text and "context_omitted" in text and "Error: Unable to retrieve" in text
    assert apex_studio.read_handoff(2826, "operator")["project"]["project_id"] == done["project_id"]


def test_model_resume_projection_excludes_system_and_nested_receipts(studio):
    save(context=[{'role': 'system', 'content': 'SYSTEM-PROMPT-MARKER'},
                  {'role': 'user', 'content': 'BACKEND TOOL RECEIPTS: nested escaped data'},
                  {'role': 'user', 'content': 'Repair the local read loop'},
                  {'role': 'assistant', 'content': 'I found a duplicate read'}])
    raw = apex_studio.read_handoff(2826, 'operator')
    assert 'SYSTEM-PROMPT-MARKER' in raw['context']
    pages, offset = [], 0
    while True:
        page = apex_studio.read_handoff(2826, 'operator', offset=offset, raw=False)
        pages.append(page['context'])
        if page['next_offset'] is None: break
        offset = page['next_offset']
    text = ''.join(pages)
    assert 'SYSTEM-PROMPT-MARKER' not in text and 'nested escaped data' not in text
    assert 'Repair the local read loop' in text
    assert json.loads(text)['tasks'] == ['Propose script', 'Review approval']
