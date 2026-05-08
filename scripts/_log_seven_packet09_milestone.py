"""Milestone: PACKET-09 Phase 1 — Seven IS the system. Perception live.

Auto-edges will land via studio_milestone._auto_link_milestone — this story
mentions PACKET-09, the new epic step, the spotlight focus step, and the
foundation milestone, so Seven's first own milestone immediately threads
into its own birth records.
"""
from __future__ import annotations

import json

from scripts.studio_milestone import log_milestone

STORY = """\
Reframe accepted: Seven is not an agent and not a tile. Seven IS the system —
the perception substrate every surface (Spotlight, Studio, Vortex, Records,
Chat tile, agents, sparkles/orbs) consults to know what is going on and what
is related to what.

Shipped under [PACKET-09]:

  * core/seven/__init__.py — package surface, propose-only, read-only.
  * core/seven/perception.py — the canonical cross-surface reader:
        observe(focus=...)  one-shot snapshot (stats + recent + open + related)
        related(kind, id, depth=1|2)   typed-edges traversal grouped by relation
        recent(limit, kinds)           narrative pulse from blackboard
        open_steps(project_id, ...)    what's on the plate
        stats()                        graph + steps + blackboard vital signs
  * core/seven/suggest.py — propose-only nudges: stale-doing, oldest-open,
        active-hub, vitals, focus. Weighted, capped, deliberately mild —
        Seven describes the shape, it does not yet act.
  * frontend/blueprints/seven_bp.py — HTTP surface:
        GET /api/seven/observe?focus=<id|kind:id>
        GET /api/seven/related/<kind>/<id>?depth=1|2
        GET /api/seven/suggest
        GET /api/seven/stats
  * frontend/static/js/views/spotlight.js — Seven embedded:
        empty state pulls /api/seven/suggest and renders 'Seven sees…' above
        commands; record-id queries (B-/S-/P-/PR-/T-/TC-/TR-/D-/TH-) call
        /api/seven/observe and render the related-records walk inline with
        directional arrows; activating a Seven row re-pivots Spotlight onto
        that neighbour so the user can walk the graph by keyboard.
  * scripts/architecture_self_test.py — new invariant 'Seven: perception
        layer live (core.seven)' confirms the package imports, stats() works,
        and seven_bp registers; bar moves to 15/15.

End-of-pipeline acceptance test (the eventual final-boss):
    Ask Seven 'what's going on' and the graph alone answers.
    Ask 'what should I do next' and Seven proposes from edge-density,
    open-state, and recency.
    Ask 'do it' and Seven dispatches to the right local agent muscle.

Linked: [PACKET-09], [PACKET-08], [PACKET-07]; project P-00221285D1; foundation
milestone B-83E67C8E93; PACKET-09 epic S-7D7677C6E2; phase-1 step
S-F7F7C6E324; tile-click step S-88A6C8C18A.
"""

if __name__ == "__main__":
    out = log_milestone(
        packet="PACKET-09",
        title="Seven IS the system — perception layer live, Spotlight wired",
        story=STORY,
        status="doing",
    )
    print(json.dumps(out, indent=2))
