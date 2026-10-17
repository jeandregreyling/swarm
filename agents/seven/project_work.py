"""Deterministic project-aware execution lane for Seven."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from agents.seven.companion_contract import context_handoff_map


def _db_path() -> Path:
    configured = os.environ.get("SWARM_MEMORY_DB") or os.environ.get("SWARM_DB_PATH")
    return Path(configured) if configured else Path(__file__).resolve().parents[2] / "swarm_memory.db"


def select_and_record(message: str) -> dict:
    """Select one bounded live Studio step and record Seven's focus handoff."""
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """SELECT s.step_id, s.project_id, s.title, s.description, s.status, s.owner,
                      s.owner_route, p.name AS project_name
               FROM project_steps s
               JOIN projects p ON p.project_id=s.project_id
               WHERE p.status='active' AND s.status IN ('doing','todo','blocked')
               ORDER BY
                 CASE WHEN lower(s.owner)='seven' AND s.status='doing' THEN 0
                      WHEN lower(s.owner)='seven' THEN 1
                      WHEN s.status='doing' THEN 2
                      WHEN s.status='blocked' THEN 3 ELSE 4 END,
                 s.order_idx ASC, COALESCE(s.updated_at, s.created_at) ASC
               LIMIT 1"""
        ).fetchone()
        if not row:
            return {"ok": False, "blocker": "No active Studio step is available."}
        step = dict(row)
        mapping = context_handoff_map(
            message,
            source="ghost",
            target="seven",
            evidence=[
                f"studio-project:{step['project_id']}",
                f"studio-step:{step['step_id']}",
            ],
            unresolved=[step["title"]],
            return_to="ghost",
        )
        summary = (
            f"Seven project-aware selection: project={step['project_id']} step={step['step_id']} "
            f"status={step['status']} owner={step['owner']} return_to=ghost. "
            f"Mapped obligations={mapping['obligations']}"
        )
        conn.execute(
            """INSERT INTO project_step_evidence
               (project_id, step_id, source_type, source_ref, summary, status)
               VALUES (?, ?, 'seven', ?, ?, 'ok')""",
            (
                step["project_id"],
                step["step_id"],
                f"seven:project-aware-selection:{int(time.time())}",
                summary,
            ),
        )
        conn.commit()
        return {"ok": True, "step": step, "mapping": mapping, "evidence": summary}
    except Exception as exc:
        return {"ok": False, "blocker": f"{type(exc).__name__}: {exc}"}
    finally:
        conn.close()


def response(message: str) -> str:
    result = select_and_record(message)
    if not result.get("ok"):
        return (
            "I inspected live Studio but could not select a bounded task. "
            f"DEOS blocker: {result.get('blocker')}"
        )
    step = result["step"]
    mapping = result["mapping"]
    return (
        "I inspected live Studio and selected one bounded task.\n"
        f"Project: {step['project_name']} ({step['project_id']})\n"
        f"Step: {step['title']} ({step['step_id']})\n"
        f"State: {step['status']} · owner={step['owner']}\n"
        f"CHM: ghost -> seven -> {mapping['return_to']}; evidence={mapping['evidence']}; "
        f"unresolved={mapping['unresolved']}\n"
        "DEOS action: work only this step, verify the real path, then write completion or the exact blocker back to Studio."
    )

