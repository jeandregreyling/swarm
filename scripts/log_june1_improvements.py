#!/usr/bin/env python3
from __future__ import annotations

from core.knowledge.projects import (
    add_blackboard_note,
    create_project,
    list_blackboard_notes,
)

PROJECT_ID = "P-00221285D1"
CONTENT = """[PACKET-06] MILESTONE - June 1 Improvements
==========================================
Date: 2026-06-01

Summary of improvements:
- Home quick-access collapse tightened for compact desktop/mobile behavior.
- Home chat opacity linked to occupancy/theme behavior.
- Empty-pillars first-run banner copy clarified and help link added.
- Windows launcher hardened for native-window-first startup with UNC-safe venv handling and execution-first fallback.
- Samsung tablet GPU/capability visibility improvements reflected in app-facing surfaces.

Validation:
- Frontend/Android touched files validated without new file-level errors.
- Windows launcher smoke path reached healthy runtime and served UI assets.
"""


def main() -> int:
    target_project = PROJECT_ID
    try:
        note = add_blackboard_note(target_project, content=CONTENT, kind="milestone", author="codex")
    except ValueError as e:
        if "unknown project_id" not in str(e):
            raise
        fallback = create_project(
            name="June 1 Improvements",
            description="Backfilled milestone log for June 1 UI and launcher improvements.",
            methodology="mixed",
            owner="seven",
        )
        target_project = fallback.get("project_id")
        note = add_blackboard_note(target_project, content=CONTENT, kind="milestone", author="codex")
    notes = list_blackboard_notes(target_project, status="active", limit=5)
    created_note_id = note.get("note_id") if isinstance(note, dict) else str(note)
    print(f"project_id={target_project}")
    print(f"created_note_id={created_note_id}")
    if notes:
        latest = notes[0]
        headline = (latest.get("content") or "").splitlines()[0]
        print(f"latest_note_id={latest.get('note_id')}")
        print(f"latest_kind={latest.get('kind')}")
        print(f"latest_headline={headline}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
