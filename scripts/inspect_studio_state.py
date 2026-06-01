#!/usr/bin/env python3
"""One-shot inventory of open Studio items for review."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.knowledge.projects import (
    list_projects,
    list_steps,
    list_blackboard_notes,
)


def main() -> int:
    projs = list_projects(limit=100) or []
    active = [p for p in projs if (p.get("status") or "active") == "active"]
    print(f"=== PROJECTS active={len(active)} total={len(projs)} ===")
    for p in active:
        print(f"  {p.get('project_id')}  prio={p.get('priority',0):>2}  {p.get('name')}")

    open_states = ("todo", "in_progress", "blocked", "review", "doing", "pending")
    targets = [p.get("project_id") for p in active] + ["P-00221285D1"]
    seen = set()
    for target in targets:
        if not target or target in seen:
            continue
        seen.add(target)
        print()
        print(f"=== STEPS in {target} ===")
        try:
            steps = list_steps(target) or []
        except Exception as exc:
            print(f"  steps error: {exc}")
            steps = []
        open_s = [s for s in steps if (s.get("status") or "todo") in open_states]
        print(f"  open={len(open_s)}  total={len(steps)}")
        for s in open_s[:80]:
            title = (s.get("title") or "").strip()
            print(f"  [{s.get('status'):11}] {s.get('step_id')}  {title[:90]}")

        print(f"--- recent blackboard notes in {target} ---")
        notes = list_blackboard_notes(target, status="active", limit=6) or []
        for n in notes:
            head = (n.get("content") or "").splitlines()[0][:110]
            print(f"  {n.get('note_id')} [{n.get('kind','note')}] {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
