#!/usr/bin/env python3
"""Bootstrap the June 2026 plan-mode coordination project in Studio.

Creates (or reuses) a coordination project, seeds canonical cross-stream steps,
links currently-active project IDs in a milestone-style blackboard note, and
prints a JSON summary for automation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.knowledge.projects import add_blackboard_note
from core.knowledge.projects import add_step
from core.knowledge.projects import create_project
from core.knowledge.projects import list_projects
from core.knowledge.projects import list_steps

PROJECT_NAME = "Plan Mode Execution - June 2026"
IDEMPOTENCY_KEY = "plan-mode-2026-06-01"

SEED_STEPS = [
    (
        "[PHASE-0] Preflight baseline and guardrails",
        "Verify swap>=32GB, NTFS mount health, backup freshness, API reachability, and capture evidence.",
    ),
    (
        "[PHASE-1] Reconcile all active Studio projects",
        "Classify open steps by execute-now/blocked/deferred and identify cross-project dependencies.",
    ),
    (
        "[PHASE-2] Potato Farm remote-first stabilization",
        "Repair Android telemetry and reconnect reliability, then validate remote inference fallback.",
    ),
    (
        "[PHASE-3] Windows app sync alignment",
        "Validate launcher paths, git drift checks, and node identity consistency against contracts.",
    ),
    (
        "[PHASE-4] GitHub backup and drift audit",
        "Run backup->verify->origin drift checks and capture audit artifacts in Studio.",
    ),
    (
        "[PHASE-5] LLM chunking validation",
        "Run recursive-chunk API checks, boundary cases, persistence checks, and focused regression tests.",
    ),
    (
        "[PHASE-6] Integrated E2E acceptance and closeout",
        "Execute single acceptance pass and close touched steps with residual risk notes where needed.",
    ),
]


def _active_projects() -> List[Dict]:
    active = list_projects(status="active", limit=300) or []
    active.sort(key=lambda p: (-(p.get("priority") or 0), p.get("project_id") or ""))
    return active


def _ensure_steps(project_id: str) -> Dict[str, List[str]]:
    existing = {((s.get("title") or "").strip()): s.get("step_id") for s in (list_steps(project_id) or [])}
    created: List[str] = []
    reused: List[str] = []
    for title, description in SEED_STEPS:
        if title in existing:
            reused.append(existing[title] or "")
            continue
        step_id = add_step(project_id, title, description=description, owner="seven")
        if step_id:
            created.append(step_id)
    return {"created": created, "reused": reused}


def _log_link_note(project_id: str, active_projects: List[Dict]) -> str:
    top = []
    for row in active_projects[:50]:
        pid = row.get("project_id") or ""
        name = row.get("name") or ""
        status = row.get("status") or "active"
        prio = row.get("priority") or 0
        if not pid or pid == project_id:
            continue
        top.append(f"- {pid} [prio={prio} status={status}] {name}")

    content = (
        "[PLAN-MODE] Coordination kickoff (June 2026)\n"
        "=======================================\n"
        "This project coordinates cross-stream execution and evidence across all active Studio projects.\n"
        "\n"
        "Linked active projects:\n"
        f"{chr(10).join(top) if top else '- (none found)'}\n"
        "\n"
        "Initial gates:\n"
        "1) Preflight baseline complete\n"
        "2) Backup+verify green\n"
        "3) Origin drift checked\n"
        "4) Chunking smoke pass\n"
        "5) Android remote-first path stable\n"
    )
    return add_blackboard_note(project_id, content, author="codex", kind="milestone") or ""


def main() -> int:
    active = _active_projects()

    project_id = create_project(
        PROJECT_NAME,
        description=(
            "Execution rail for swap-backed plan mode: potato farm repair, Android remote-first, "
            "Windows sync, GitHub backup/sync audit, and chunking validation."
        ),
        methodology="agile",
        owner="seven",
        idempotency_key=IDEMPOTENCY_KEY,
        tags=["plan-mode", "potato-farm", "android", "windows", "chunking", "backup", "june-2026"],
    )
    if not project_id:
        print(json.dumps({"ok": False, "error": "failed to create/reuse plan-mode project"}, indent=2))
        return 1

    step_summary = _ensure_steps(project_id)
    note_id = _log_link_note(project_id, active)

    out = {
        "ok": True,
        "project_id": project_id,
        "project_name": PROJECT_NAME,
        "active_project_count": len(active),
        "seed_steps_created": step_summary["created"],
        "seed_steps_reused": step_summary["reused"],
        "kickoff_note_id": note_id,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
