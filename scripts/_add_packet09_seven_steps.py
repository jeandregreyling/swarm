"""Add a [PACKET-09] Seven scaffold epic + first sub-step under it.

PACKET-09 is the umbrella for "Seven IS the system" — the perception layer,
the propose-only authority, and every later phase that consumes the brain.
"""
from __future__ import annotations

import json

from scripts.studio_milestone import _http


def main() -> None:
    PROJECT = "P-00221285D1"

    epic = _http("POST", f"/api/knowledge/projects/{PROJECT}/steps", {
        "title": "[PACKET-09] Seven IS the system — perception layer + propose-only brain",
        "description": (
            "Seven is not a tile and not an agent. Seven is the substrate every "
            "surface (Spotlight, Studio, Vortex, Records, Chat tile, agents, "
            "sparkles/orbs) consults to know what is going on and what is "
            "related to what.\n\n"
            "PACKET-09 owns: core.seven.perception (canonical reader), "
            "core.seven.suggest (propose-only nudges), blueprints.seven_bp "
            "(/api/seven/observe|related|suggest|stats), and the Seven "
            "self-test invariant. Phase 1 plugs Seven into Spotlight as the "
            "empty-state and the record-id focus mode. Subsequent phases "
            "consume /api/seven/* from Studio, Vortex, Records, Diamond, agents."
        ),
        "status": "doing",
        "owner": "seven",
    })
    epic_id = (epic or {}).get("step_id")

    sub = _http("POST", f"/api/knowledge/projects/{PROJECT}/steps", {
        "title": "[PACKET-09] Phase 1 — Seven embedded in Spotlight (empty-state + record focus)",
        "description": (
            "Spotlight (Ctrl+Space) is Seven's most direct input. On open with "
            "no query, render Seven's suggestions section ('Seven sees ...') "
            "above commands. When the query matches a record id pattern "
            "(B-/S-/P-/PR-/T-/TC-/TR-/D-/TH-), call /api/seven/observe and "
            "render the related-records walk inline with arrow direction. "
            "Activating a Seven row re-pivots Spotlight onto that neighbour "
            "so the user can walk the graph by keyboard."
        ),
        "status": "done",
        "owner": "seven",
    })

    print(json.dumps({"epic": epic, "sub": sub, "epic_id": epic_id}, indent=2))


if __name__ == "__main__":
    main()
