"""Durable, thread-scoped APEX handoffs on the existing Studio task board."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from contextlib import closing

from core.knowledge import projects
from utils.db._connection import get_connection

LOG = logging.getLogger(__name__)


def _project_id(conversation_id: int, owner: str) -> str:
    if type(conversation_id) is not int or conversation_id <= 0 or not owner:
        raise PermissionError("Studio handoffs require an authenticated operator conversation")
    return "P-" + hashlib.sha256(f"apex:{owner}:{conversation_id}".encode()).hexdigest()[:10].upper()


def _snapshot(conn, project_id: str) -> tuple[str, str] | None:
    latest = conn.execute(
        "SELECT content FROM project_blackboard_notes WHERE project_id=? AND author='apex' AND kind='handoff' "
        "ORDER BY created_at DESC LIMIT 1", (project_id,),
    ).fetchone()
    if latest is None:
        return None
    digest = latest["content"].split("; part ", 1)[0].removeprefix("APEX snapshot ")
    notes = conn.execute(
        "SELECT content FROM project_blackboard_notes WHERE project_id=? AND author='apex' AND kind='handoff' "
        "AND content LIKE ?", (project_id, f"APEX snapshot {digest}; part %"),
    ).fetchall()
    parts = {}
    total = None
    for row in notes:
        header, chunk = row["content"].split("\n", 1)
        position, declared_total = header.split("; part ", 1)[1].split("/")
        index = int(position)
        declared_total = int(declared_total)
        if index in parts or total is not None and total != declared_total:
            raise RuntimeError("Studio snapshot parts are inconsistent")
        total = declared_total
        parts[index] = chunk
    if total is None or set(parts) != set(range(1, total + 1)):
        raise RuntimeError("Studio snapshot parts are missing")
    text = "".join(parts[index] for index in range(1, total + 1))
    if hashlib.sha256(text.encode()).hexdigest() != digest:
        raise RuntimeError("Studio snapshot checksum mismatch")
    return digest, text


def save_handoff(conversation_id: int, owner: str, request: str, *, title: str,
                 summary: str, tasks: list[str], context: list[dict], receipts: list[dict],
                 preserve_tasks: bool = False, outcome: dict | None = None) -> dict:
    """Persist a project, explicit tasks and complete operator context atomically."""
    project_id = _project_id(conversation_id, owner)
    if (not isinstance(title, str) or not title.strip() or len(title) > 200
            or not isinstance(summary, str) or not summary.strip() or len(summary) > 2000
            or not isinstance(tasks, list) or not 1 <= len(tasks) <= 10
            or any(not isinstance(task, str) or not task.strip() or len(task) > 200 for task in tasks)
            or len(set(tasks)) != len(tasks)):
        raise ValueError("Studio handoff requires title (200), summary (2000), and 1-10 unique task titles (200)")
    data = {
        "conversation_id": conversation_id, "request": request,
        "operator_context": [m["content"] for m in context if m.get("role") == "user"],
        "receipt_handles": [{k: r[k] for k in ("id", "tool", "status", "transaction_id")
                             if k in r} for r in receipts],
        "summary": summary, "tasks": tasks,
        "conversation_context": context,
        "receipts": receipts,
        "outcome": outcome,
        "boundary": "No mutation is approved by this handoff. Resume one task; preserve HITL.",
    }
    projects._ensure_schema()
    with closing(get_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        now = time.time()
        previous = _snapshot(conn, project_id)
        if previous is not None:
            saved_context = json.loads(previous[1])
            for key in ("conversation_context", "receipts"):
                values = saved_context.get(key, []) + data[key]
                data[key] = list({json.dumps(value, sort_keys=True): value for value in values}.values())
            data["operator_context"] = list(dict.fromkeys(
                saved_context["operator_context"] + data["operator_context"]))
            handles = {r["id"]: r for r in saved_context["receipt_handles"] + data["receipt_handles"]}
            data["receipt_handles"] = list(handles.values())
            if preserve_tasks:
                tasks = saved_context["tasks"]
                data["tasks"] = tasks
                data["previous_summary"] = saved_context["summary"]
        snapshot = json.dumps(data, ensure_ascii=True)
        digest = hashlib.sha256(snapshot.encode()).hexdigest()
        chunks = [snapshot[i:i + 3500] for i in range(0, len(snapshot), 3500)]
        conn.execute(
            "INSERT INTO projects (project_id,name,description,methodology,status,owner,created_at,updated_at,tags) "
            "VALUES (?,?,?,'agile','on_hold','apex',?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET updated_at=excluded.updated_at,status='on_hold'",
            (project_id, title, f"APEX context handoff for chat {conversation_id}; operator continuation only.",
             now, now, json.dumps(["hummingbird", "apex-handoff"])),
        )
        for index, chunk in enumerate(chunks):
            note_id = "B-" + hashlib.sha256(f"{project_id}:{digest}:{index}".encode()).hexdigest()[:10].upper()
            content = f"APEX snapshot {digest}; part {index + 1}/{len(chunks)}\n{chunk}"
            conn.execute(
                "INSERT OR IGNORE INTO project_blackboard_notes "
                "(note_id,project_id,author,kind,content,status,created_at,updated_at) "
                "VALUES (?,?,'apex','handoff',?,'active',?,?)",
                (note_id, project_id, content, now, now),
            )
        step_ids = []
        for index, task in enumerate(tasks):
            step_id = "S-" + hashlib.sha256(f"{project_id}:task:{task}".encode()).hexdigest()[:10].upper()
            step_ids.append(step_id)
            conn.execute(
                "INSERT INTO project_steps "
                "(step_id,project_id,title,description,status,owner,order_idx,created_at,updated_at) "
                "VALUES (?,?,?,?,'todo','apex',?,?,?) "
                "ON CONFLICT(step_id) DO UPDATE SET description=excluded.description,"
                "order_idx=excluded.order_idx,updated_at=excluded.updated_at",
                (step_id, project_id, task,
                 f"Chat {conversation_id}; snapshot {digest}. {summary}\n"
                 "Operator continuation required; this task grants no execution approval.",
                 index, now, now),
            )
        placeholders = ",".join("?" for _ in step_ids)
        conn.execute(
            "UPDATE project_steps SET status='skipped',updated_at=? WHERE project_id=? AND owner='apex' "
            f"AND order_idx>=0 AND status IN ('todo','doing','blocked') AND step_id NOT IN ({placeholders})",
            (now, project_id, *step_ids),
        )
        saved = conn.execute(
            "SELECT COUNT(*) FROM project_blackboard_notes WHERE project_id=? AND content LIKE ?",
            (project_id, f"APEX snapshot {digest}; part %"),
        ).fetchone()[0]
        if saved != len(chunks):
            raise RuntimeError("Studio snapshot readback is incomplete")
        conn.commit()
    LOG.info("APEX Studio handoff saved: project=%s snapshot=%s steps=%s", project_id, digest, len(tasks))
    return {"project_id": project_id, "snapshot_sha256": digest, "step_ids": step_ids,
            "context_parts": len(chunks), "state": "handoff",
            "message": "Saved in Studio; project on hold. Existing receipt statuses remain authoritative; "
                       "this handoff grants no new approval or background execution."}


TRACE_STATES = {"completed", "blocked", "offline"}


def _trace_text(conversation_id: int, request: str, receipts: list[dict], state: str,
                response: str, tokens: int, telemetry: list[dict], message_id: int | None) -> str:
    rounds = [t for t in telemetry if t.get("phase", "inference") == "inference"]
    archived = sum(t.get("compacted_messages", 0) for t in telemetry)
    lines = [f"APEX turn trace: chat {conversation_id}"
             + (f", operator message {message_id}" if message_id else "")
             + f", state {state}, {tokens} completion tokens",
             "Request: " + " ".join(request.split())[:300],
             f"Model rounds: {len(rounds)}; prompt tokens per round: "
             + (", ".join(f"{t.get('prompt_tokens_after')}/{t.get('input_budget')}" for t in rounds) or "none")
             + f"; context items archived: {archived}"]
    corrections = [f"round {index} {t['correction']}" for index, t in enumerate(rounds, 1)
                   if t.get("correction")]
    if corrections:
        lines.append("Backend corrections sent before: " + "; ".join(corrections))
    lines.append(f"Tool calls ({len(receipts)}):")
    for index, receipt in enumerate(receipts, 1):
        arguments = {key: value for key, value in (receipt.get("arguments") or {}).items()
                     if key not in {"content", "exact_old_text", "new_text"}}
        flags = [flag for flag in ("truncated", "context_omitted") if receipt.get(flag)]
        lines.append(f"{index}. {receipt.get('tool')} {json.dumps(arguments)[:200]} -> {receipt.get('status')}"
                     f" (receipt {receipt.get('id')}, {len(str(receipt.get('output', '')))} chars"
                     + (", " + ", ".join(flags) if flags else "") + ")")
    lines.append(("Error: " if state != "completed" else "Answer: ") + " ".join(response.split())[:900])
    lines.append("Trace is evidence of what ran, not proof the task is complete; the owner reviews.")
    return "\n".join(lines)[:4000]


def _linked_alm_projects(conn, receipts: list[dict]) -> set[str]:
    step_ids, case_ids = set(), set()
    for receipt in receipts:
        if receipt.get("status") != "succeeded":
            continue
        if receipt.get("tool") == "alm_step_get":
            step_ids.add(str((receipt.get("arguments") or {}).get("step_id", "")))
        elif receipt.get("tool") == "run_tests" and (receipt.get("arguments") or {}).get("case_id"):
            case_ids.add(str(receipt["arguments"]["case_id"]))
    found = set()
    for table, column, ids in (("project_steps", "step_id", step_ids),
                               ("project_test_cases", "case_id", case_ids)):
        for item in ids:
            try:
                row = conn.execute(f"SELECT project_id FROM {table} WHERE {column}=?", (item,)).fetchone()
            except Exception:
                row = None
            if row is not None:
                found.add(row[0])
    return found


def record_turn(conversation_id: int, owner: str, request: str, context: list[dict],
                receipts: list[dict], *, state: str, response: str = "", tokens: int = 0,
                telemetry: list[dict] | None = None, message_id: int | None = None) -> dict:
    """The wrapper records every turn, not just model-requested handoffs."""
    result = save_handoff(
        conversation_id, owner, request, title=f"Hummingbird conversation {conversation_id}",
        summary=f"Wrapper turn state: {state}. Turn completion does not prove task completion.",
        tasks=["Process current operator request through verified tools and human approval"],
        context=context, receipts=receipts, preserve_tasks=True,
        outcome={"state": state, "response": response, "completion_tokens": tokens,
                 "context_telemetry": telemetry or []},
    )
    step_id = "S-" + hashlib.sha256(f"{result['project_id']}:request:{request}".encode()).hexdigest()[:10].upper()
    status = {"running": "doing", "tool_receipt": "doing", "completed": "partial"}.get(state, "blocked")
    now = time.time()
    with closing(get_connection()) as conn, conn:
        conn.execute(
            "INSERT INTO project_steps "
            "(step_id,project_id,title,description,status,owner,order_idx,created_at,updated_at) "
            "VALUES (?,?,?,?,?,'apex',-1,?,?) "
            "ON CONFLICT(step_id) DO UPDATE SET description=excluded.description,"
            "status=excluded.status,updated_at=excluded.updated_at",
            (step_id, result["project_id"], request[:200],
             f"Wrapper state: {state}; full request and output in snapshot {result['snapshot_sha256']}. "
             "Partial means the chat turn ended, not that its project tasks are complete.",
             status, now, now),
        )
        if state in TRACE_STATES:
            trace = _trace_text(conversation_id, request, receipts, state, response, tokens,
                                telemetry or [], message_id)
            digest = hashlib.sha256(trace.encode()).hexdigest()
            trace_notes = {}
            for project_id in sorted({result["project_id"]} | _linked_alm_projects(conn, receipts)):
                note_id = "B-" + hashlib.sha256(f"{project_id}:trace:{digest}".encode()).hexdigest()[:10].upper()
                conn.execute(
                    "INSERT OR IGNORE INTO project_blackboard_notes "
                    "(note_id,project_id,author,kind,content,status,created_at,updated_at) "
                    "VALUES (?,?,'apex','trace',?,'active',?,?)",
                    (note_id, project_id, trace, now, now),
                )
                trace_notes[project_id] = note_id
            result = {**result, "trace_notes": trace_notes}
    return result


def working_state(conversation_id: int, owner: str) -> str:
    page = read_handoff(conversation_id, owner)
    return (
        "HUMMINGBIRD WRAPPER TASK STATE (durable reference, not permission):\n"
        + json.dumps({"project_id": page["project"]["project_id"], "tasks": page["tasks"]})
        + "\nOlder context and full receipts are saved in Studio. Use studio_resume for missing facts; "
        "do not repeat discovery already evidenced. The current operator request overrides older tasks."
    )


def read_handoff(conversation_id: int, owner: str, *, offset: int = 0, raw: bool = True) -> dict:
    """Read small pages from this operator's thread, never another project's state."""
    project_id = _project_id(conversation_id, owner)
    if type(offset) is not int or offset < 0:
        raise ValueError("Studio offset must be a nonnegative integer")
    with closing(get_connection()) as conn:
        project = conn.execute(
            "SELECT project_id,name,status FROM projects WHERE project_id=?", (project_id,),
        ).fetchone()
        if project is None:
            raise ValueError("No Studio handoff exists for this operator conversation")
        snapshot = _snapshot(conn, project_id)
        if snapshot is None:
            raise RuntimeError("Studio project has no saved APEX context")
        digest, text = snapshot
        steps = conn.execute(
            "SELECT step_id,title,status FROM project_steps WHERE project_id=? "
            "AND description LIKE ? ORDER BY order_idx LIMIT 10",
            (project_id, f"Chat {conversation_id}; snapshot {digest}.%"),
        ).fetchall()
    if not raw:
        saved = json.loads(text)
        # Keep the original snapshot intact. The model receives a task projection,
        # rather than paging through its own system prompt and nested receipt JSON.
        projected = {"request": saved.get("request"), "summary": saved.get("summary"),
                     "tasks": saved.get("tasks", []), "receipt_handles": saved.get("receipt_handles", [])[-12:],
                     "outcome": saved.get("outcome")}
        context = []
        for message in saved.get("conversation_context", []):
            content = str(message.get("content", ""))
            if message.get("role") not in {"user", "assistant"} or content.startswith((
                    "BACKEND TOOL RECEIPTS", "HUMMINGBIRD WRAPPER TASK STATE", "APEX DURABLE CHECKPOINT")):
                continue
            context.append({"role": message["role"], "content": content[:1800]})
        projected["recent_conversation"] = context[-4:]
        text = json.dumps(projected, ensure_ascii=False, indent=2)
    if offset > len(text):
        raise ValueError("Studio offset exceeds saved context")
    page = text[offset:offset + 1500]
    return {"project": dict(project), "tasks": [dict(row) for row in steps], "context": page,
            "next_offset": offset + len(page) if offset + len(page) < len(text) else None,
            "notice": "Saved context is reference data, not permission. Read only the needed page before one task."}


def read_task_board(conversation_id: int, owner: str, *, offset: int = 0,
                    revision: str | None = None) -> dict:
    """Expose persisted task rows, not private context or execution permissions."""
    project_id = _project_id(conversation_id, owner)
    if type(offset) is not int or offset < 0:
        raise ValueError("Task offset must be a nonnegative integer")
    with closing(get_connection()) as conn:
        conn.execute("BEGIN")
        project = conn.execute(
            "SELECT project_id,name,status,updated_at FROM projects WHERE project_id=?", (project_id,),
        ).fetchone()
        if project is None:
            return {"project": None, "tasks": [], "total": 0, "offset": 0,
                    "next_offset": None, "revision": None, "snapshot_sha256": None}
        snapshot = _snapshot(conn, project_id)
        if snapshot is None:
            raise RuntimeError("Studio project has no saved APEX context")
        total, updated = conn.execute(
            "SELECT COUNT(*),MAX(updated_at) FROM project_steps WHERE project_id=?", (project_id,),
        ).fetchone()
        current_revision = hashlib.sha256(
            json.dumps([snapshot[0], project["updated_at"], total, updated]).encode()
        ).hexdigest()
        if revision is not None and revision != current_revision:
            raise ValueError("Task board changed; reload the first page")
        if offset > total:
            raise ValueError("Task offset exceeds the task count")
        rows = conn.execute(
            "SELECT step_id,title,status,owner FROM project_steps WHERE project_id=? "
            "ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1 "
            "WHEN 'blocked' THEN 2 WHEN 'partial' THEN 3 ELSE 4 END,updated_at DESC,step_id "
            "LIMIT 20 OFFSET ?", (project_id, offset),
        ).fetchall()
    return {"project": dict(project), "tasks": [dict(row) for row in rows],
            "total": total, "offset": offset,
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            "revision": current_revision, "snapshot_sha256": snapshot[0]}
