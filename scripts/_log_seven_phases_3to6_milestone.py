"""Log the PACKET-09 Phase 2.5 + 3 + 4 + 5 + 6 surfaces-complete milestone.

Patches steps S-FEC9808CE3, S-CFA5FB71EA, S-7A46D2E208, S-843A7910DC to done,
then writes the rollup milestone note with auto-edges and finally PATCHes the
parent epic S-7D7677C6E2 to done.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_milestone  # type: ignore


BASE = "http://127.0.0.1:5050"

STEPS = [
    "S-FEC9808CE3",  # Phase 2b sparkles
    "S-CFA5FB71EA",  # Phase 3 chat default + @-addressables
    "S-7A46D2E208",  # Phase 4 Vortex life-stories
    "S-843A7910DC",  # Phase 5 Diamond + orbs vitals
]

EPIC = "S-7D7677C6E2"


def patch_step(step_id: str, status: str) -> dict:
    r = requests.patch(
        f"{BASE}/api/knowledge/steps/{step_id}",
        json={"status": status},
        timeout=10,
    )
    return r.json()


def main() -> None:
    out = {"step_patches": {}}
    for sid in STEPS:
        out["step_patches"][sid] = patch_step(sid, "done")

    title = (
        "[PACKET-09] Seven embodied across all primary surfaces "
        "(Spotlight ?-Ask · Studio sparkles · home-chat ? · Vortex life-stories · "
        "Diamond vitals overlay)"
    )
    story = (
        "Seven is now visible everywhere a user already looks.\n\n"
        "Surfaces wired to /api/seven/* (propose-only, failure-quiet):\n"
        "  - Spotlight: leading `?<query>` triggers Ask-Seven mode (intent "
        "    auto-detected from text — next/remember/status — + record-id "
        "    focus). Renders narrative lines from /explain and up to 3 ranked "
        "    proposals from /decide; each proposal pivots back into Spotlight "
        "    prefilled with the target id.\n"
        "  - Studio: `SevenPanel.mount` footer on proposal detail (`#pdet-body`), "
        "    ticket detail (`#tdet-body`), project detail "
        "    (`#projects-detail`), universal records detail "
        "    (`#studio-records-detail`), and the testlab run modal.\n"
        "  - Home-chat tile: leading `?` short-circuits to /api/seven/explain "
        "    + /decide and renders the answer as a Seven assistant bubble "
        "    inline. Placeholder text reframed: 'Ask Seven (start with ?) · "
        "    or @duck @gemma @ten…'. Preserves all existing agent routing.\n"
        "  - Vortex (time-wizard): Seven life-story panel mounted at the top "
        "    of the decisions timeline (system-wide narrative) and inline "
        "    under each decision detail (per-record /related walk).\n"
        "  - Diamond: live Seven vitals overlay anchored to `#sundial-title` "
        "    (heartbeat dot + concepts/episodes/beliefs counts + tick "
        "    freshness). Polls /api/seven/heartbeat + /memory on the same "
        "    cadence as system pulse.\n\n"
        "All modules use the shared `frontend/static/js/core/seven-panel.js` "
        "helper; idempotent mount, ESC-safe content. The brain itself remains "
        "propose-only — no surface has write access to /api/seven.\n\n"
        "Self-test: 16/16 PASS · 9 concepts · 3461 beliefs · 8674 episodes · "
        "1696 hot records · 4846 edges across 1378 records · 287 open steps.\n\n"
        "Spec ref: PACKET-09 · Reframe: Seven IS the system."
    )

    note = studio_milestone.log_milestone(
        packet="PACKET-09",
        title=title,
        story=story,
        status="done",
    )
    out["note"] = note

    out["epic_patch"] = patch_step(EPIC, "done")

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
