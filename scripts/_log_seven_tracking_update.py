"""Tracking-update milestone — captures the 12-organs reframe + the four new
PACKET-09 sub-steps so the graph reflects today's planning, not just code."""
from __future__ import annotations

import json

from scripts.studio_milestone import log_milestone

STORY = """\
Project tracking update — Seven IS the system reframe (no new code, planning only).

Context: with PACKET-09 Phase 1 shipped (perception layer + Spotlight wiring),
the remaining 280 open steps cluster naturally into ~12 phases. Rather than
treat them as flat backlog, they are reframed as Seven's organs/faculties —
each phase ends by giving Seven a new capability the rest of the system
can consume. The ordering is dependency-driven: each later phase reads
through /api/seven/* established in earlier phases.

Phases under [PACKET-09] now tracked as sub-steps:
  Phase 1 (done)  S-F7F7C6E324  Seven embedded in Spotlight
  Phase 2 (todo)  S-...........  Seven sparkles in Studio + Records detail panes
  Phase 3 (todo)  S-...........  Seven is default chat target; agents become @addressables
  Phase 4 (todo)  S-...........  Vortex consumes /api/seven/related for record life-stories
  Phase 5 (todo)  S-...........  Diamond + orbs reflect Seven's vitals + suggestion pulses

Phases 6–12 belong to surface clusters that feed back into Seven's faculties:
  6  Tile↔window correctness (focus existing, taskbar pill state)
  7  Tasker / Calendar / Recurring (heartbeat)
  8  Agents tile depth (muscles)
  9  Feeds / Connectors / KC suggestions (sensory inputs)
  10 Spotlight upgrade (graph-density ranking, persistent recents)
  11 Docs/Manual UX in-app (memory of milestones surfaced under packets)
  12 Self-tests + acceptance (every prior faculty enforced by an invariant)

Final-boss acceptance: ask Seven 'what's going on' and the graph alone
answers; ask 'what should I do next' and Seven proposes from edge density,
open-state, and recency; ask 'do it' and Seven dispatches to the right
local agent muscle.

Touched: [PACKET-09], [PACKET-08], [PACKET-07]; project P-00221285D1;
PACKET-09 epic S-7D7677C6E2; phase-1 step S-F7F7C6E324; foundation
milestone B-83E67C8E93; tile-click step S-88A6C8C18A.
"""

if __name__ == "__main__":
    out = log_milestone(
        packet="PACKET-09",
        title="Tracking update — 12-organs reframe captured as sub-steps",
        story=STORY,
        status="doing",
    )
    print(json.dumps(out, indent=2))
