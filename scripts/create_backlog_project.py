#!/usr/bin/env python3
"""scripts/create_backlog_project.py — Seed the UI/Platform backlog as a
first-class Studio project.

Usage:
    python scripts/create_backlog_project.py

Idempotent: if a project with the same name exists, its id is reused and
missing steps/cases are topped up.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.knowledge import projects as kp  # noqa: E402

PROJECT_NAME = "UI / Platform Backlog 2026-04"
DESCRIPTION = (
    "Consolidated backlog for the Phase 3 workstream — every item here is a "
    "managed step with its own Test Lab cases. Completing a step auto-writes "
    "a Knowledge Center doc so Seven stays up to date."
)

SMALL = [
    ("Email folder structure",
     "Inbox / Sent / Drafts / Trash + Gmail label sync."),
    ("Welcome modal wiring",
     "'Show at startup' tick, top-bar '?' trigger, Local AI button."),
    ("Local AI ollama dropdown",
     "Models dropdown for pull + clickable rows for details."),
    ("Token counter under chat input",
     "chars / words / est-tokens."),
    ("Move Both-Seq into Conversation Flow",
     "Chat: 'Both Seq' button relocates into Conversation Flow section."),
    ("Collapse chat side menus into headers",
     "Left/right menu arrows fold into Threads / Agent Controls headers."),
    ("CTRL+Space tip strip relocation",
     "Tip strip → top-right under header."),
    ("Themes/Services swap top-right",
     "Swap positions of Themes and Services in top-right."),
    ("Terminal output restore pre/code",
     "Kill the extra spacing, restore copy/paste."),
]

MEDIUM = [
    ("Tile reorganization",
     "Merge Monitor+Health Digest; merge Skills+Local AI into Agents; "
     "move Memory into Knowledge; move Trace tile next to mini-trace with "
     "error/warning tags; Add-Tile becomes drag-and-drop."),
    ("Agents tile controls",
     "Per-agent keep-warm seconds editor (pushes to ollama), Hard-Kill + "
     "Unload buttons, move temperature gauges from Chat right-menu."),
    ("Sundial per-model unload buttons",
     "RAM/VRAM dropdown gets a per-loaded-model unload button."),
    ("Themes verify",
     "Confirm Hive Grid / Hive Nodes / Ambient Scene actually toggle the "
     "layers they advertise."),
    ("Feeds add/manage services",
     "Wire the add/manage services UI end-to-end."),
    ("Relay rules audit",
     "Audit relay rules and likely retire."),
]

BIG = [
    ("Single-source manual",
     "Every '?' tooltip pulls from one Library Manual section; update once "
     "→ all tiles update."),
    ("Knowledge ↔ Memory unification",
     "Obsidian-style graph + agent feed."),
    ("Reply-as-true-thread",
     "Backend message_id linking + threaded render (partial exists)."),
]


def _ensure_project() -> str:
    for p in kp.list_projects(limit=500):
        if p.get("name") == PROJECT_NAME:
            return p["project_id"]
    pid = kp.create_project(
        PROJECT_NAME,
        description=DESCRIPTION,
        methodology="mixed",
        owner="seven",
    )
    if not pid:
        raise RuntimeError("failed to create project")
    return pid


def _existing_step_titles(pid: str) -> set[str]:
    return {s.get("title", "") for s in kp.list_steps(pid)}


def _seed_group(pid: str, group_label: str, items: list[tuple[str, str]]) -> int:
    existing = _existing_step_titles(pid)
    added = 0
    for title, desc in items:
        full_title = f"[{group_label}] {title}"
        if full_title in existing:
            continue
        kp.add_step(pid, full_title, description=desc, owner="seven")
        added += 1
    return added


def main() -> int:
    pid = _ensure_project()
    s = _seed_group(pid, "SMALL", SMALL)
    m = _seed_group(pid, "MEDIUM", MEDIUM)
    b = _seed_group(pid, "BIG", BIG)
    total = s + m + b
    print(f"project_id: {pid}")
    print(f"added: small={s} medium={m} big={b} total={total}")
    print("existing steps now: {}".format(len(kp.list_steps(pid))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
