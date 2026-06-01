#!/usr/bin/env python3
"""Phase-1 inventory and blocker classification for plan-mode execution.

Produces:
- JSON report under runtime/reports/
- Studio blackboard note in the coordination project
- Phase-1 coordination step moved to 'doing'
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import sys
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.knowledge.projects import add_blackboard_note
from core.knowledge.projects import list_projects
from core.knowledge.projects import list_steps
from core.knowledge.projects import update_step_status

COORD_PROJECT_NAME = "Plan Mode Execution - June 2026"
PHASE1_TITLE = "[PHASE-1] Reconcile all active Studio projects"
OPEN_STATES = {"todo", "doing", "blocked", "in_progress", "pending", "review", "partial"}
REPORT_DIR = ROOT / "runtime" / "reports"


def _find_coord_project(active_projects: List[Dict]) -> Dict:
    for p in active_projects:
        if (p.get("name") or "").strip() == COORD_PROJECT_NAME:
            return p
    return {}


def _step_priority_bucket(title: str, project_id: str) -> Tuple[int, str]:
    t = (title or "").lower()

    # Lower number = higher priority.
    rules = [
        (10, ["lock", "contract", "sync api", "recover", "stale relay", "first-claim", "go/no-go"], "infra-blocker"),
        (20, ["potato-00", "potato-01", "potato-02", "potato-03", "potato-04", "potato-05"], "potato-foundation"),
        (30, ["potato-07", "android", "tflite", "gpu", "npu"], "android"),
        (40, ["potato-06", "windows", "desktop", "installer", "msi"], "desktop-windows"),
        (50, ["chunk", "quintum", "recursive", "knowledge center", "kc"], "chunking-kc"),
        (60, ["appcenter", "artifact"], "distribution"),
        (70, ["e2e", "acceptance", "proof"], "acceptance"),
    ]

    for prio, needles, bucket in rules:
        if any(n in t for n in needles):
            return prio, bucket

    if project_id == "P-CHAT-RELAY-RECOVERY":
        return 15, "relay"
    return 90, "general"


def _collect_open_steps(active_projects: List[Dict]) -> List[Dict]:
    rows: List[Dict] = []
    for p in active_projects:
        pid = p.get("project_id") or ""
        if not pid:
            continue
        for s in list_steps(pid) or []:
            status = (s.get("status") or "todo").lower()
            if status not in OPEN_STATES:
                continue
            title = (s.get("title") or "").strip()
            prio, bucket = _step_priority_bucket(title, pid)
            rows.append(
                {
                    "project_id": pid,
                    "project_name": p.get("name") or "",
                    "step_id": s.get("step_id") or "",
                    "title": title,
                    "status": status,
                    "priority": prio,
                    "bucket": bucket,
                }
            )
    rows.sort(key=lambda r: (r["priority"], r["project_id"], r["step_id"]))
    return rows


def _format_studio_note(rows: List[Dict], active_projects: List[Dict], report_relpath: str) -> str:
    by_bucket: Dict[str, int] = {}
    for r in rows:
        by_bucket[r["bucket"]] = by_bucket.get(r["bucket"], 0) + 1

    top = rows[:20]
    top_lines = [
        f"- {r['project_id']} :: {r['step_id']} [{r['status']}] ({r['bucket']}) {r['title']}"
        for r in top
    ]
    proj_lines = [f"- {p.get('project_id')} {p.get('name')}" for p in active_projects]
    bucket_lines = [f"- {k}: {v}" for k, v in sorted(by_bucket.items(), key=lambda kv: (-kv[1], kv[0]))]

    return (
        "[PLAN-MODE] Wave-1 inventory and blocker classification\n"
        "\n"
        "Scope: all active Studio projects.\n"
        f"Report: {report_relpath}\n"
        f"Active projects: {len(active_projects)}\n"
        f"Open steps discovered: {len(rows)}\n"
        "\n"
        "Active projects:\n"
        f"{chr(10).join(proj_lines)}\n"
        "\n"
        "Bucket counts:\n"
        f"{chr(10).join(bucket_lines)}\n"
        "\n"
        "Wave-A candidate queue (top 20):\n"
        f"{chr(10).join(top_lines)}\n"
    )


def main() -> int:
    active_projects = list_projects(status="active", limit=300) or []
    active_projects = sorted(active_projects, key=lambda p: (-(p.get("priority") or 0), p.get("project_id") or ""))

    coord = _find_coord_project(active_projects)
    if not coord:
        print(json.dumps({"ok": False, "error": "coordination project not found"}, indent=2))
        return 1

    rows = _collect_open_steps(active_projects)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    report_path = REPORT_DIR / f"plan_mode_wave1_inventory_{stamp}.json"
    payload = {
        "generated_at": int(time.time()),
        "coord_project_id": coord.get("project_id"),
        "active_projects": [
            {
                "project_id": p.get("project_id"),
                "name": p.get("name"),
                "priority": p.get("priority"),
            }
            for p in active_projects
        ],
        "open_steps": rows,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report_rel = str(report_path.relative_to(ROOT))
    note_content = _format_studio_note(rows, active_projects, report_rel)
    note_id = add_blackboard_note(coord.get("project_id"), note_content, author="codex", kind="milestone")

    phase1_step_id = None
    for s in list_steps(coord.get("project_id")) or []:
        if (s.get("title") or "").strip() == PHASE1_TITLE:
            phase1_step_id = s.get("step_id")
            break
    phase1_set = False
    if phase1_step_id:
        phase1_set = update_step_status(phase1_step_id, "doing", owner="seven")

    print(
        json.dumps(
            {
                "ok": True,
                "coord_project_id": coord.get("project_id"),
                "open_steps": len(rows),
                "report_file": str(report_path),
                "note_id": note_id,
                "phase1_step_id": phase1_step_id,
                "phase1_set_doing": phase1_set,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
