"""Foundation milestone (slot-zero): auto-edges + self-test bar + spike->step."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Make Seven the connective tissue, not just a logger. Three foundations
  installed before the long sweep so every future slice automatically
  enriches the brain instead of leaving orphan notes behind.

What we built (foundation 1 — auto-edges from milestones):
  - scripts/studio_milestone.py: every log_milestone() now scans the
    story text for record IDs (B-, S-, P-, PR-, T-, TC-, TR-, D-, TH-)
    and PACKET-XX tags, then writes typed edges from the milestone
    note into the knowledge graph:
      note  --mentions-->  every referenced record
      note  --documents--> the [PACKET-XX] epic step (if found)
      note  --child_of-->  project P-00221285D1
    All edge writes are wrapped in try/except, so a milestone never
    fails because of a graph-write hiccup. Inverse edges (parent_of,
    etc.) are written automatically by core/records/links.link().

  Catch found while wiring this: 'milestone' was not in the
  BLACKBOARD_KINDS tuple in core/knowledge/projects.py, so every
  log_milestone call this whole session had been silently rejected at
  the API layer (the status patch worked, hence the green epics, but
  no note was actually persisted). Added 'milestone' to the kinds
  tuple. Self-test will now refuse to pass if recent milestones are
  orphans — see foundation 2.

What we built (foundation 2 — self-test bar moves with us):
  - scripts/architecture_self_test.py: two new invariants.
    * 'Brain: milestone auto-links live' — samples the 20 newest
      milestone notes from project_blackboard_notes; fails if more
      than half have no outgoing edges.
    * 'Brain: home tiles all have loader branches' — parses
      terminal_base.html for every home-card data-win-id and confirms
      app.js openWindow() has a matching `id === '...'` branch (or
      the tile is on the explicit SELF_INIT_TILES allow-list, e.g.
      'feeds' which inits via IIFE inside its template). Catches
      dead-tile bugs the moment they're added.
    Bar is now 14 checks, 14 pass, 0 fail.

What we built (foundation 3 — spike\u2192step promotion rule):
  - scripts/studio_milestone.py contains the auto-link helper, but
    foundation 3 is a *convention*: every spike user names becomes a
    step row with a [PACKET-XX] prefix, gets a milestone via
    log_milestone(), and through foundation 1 its milestone note
    auto-edges to the step. We wrote the same shape today as
    S-88A6C8C18A (tile-click focus). Codified.

How to verify:
  - python3 scripts/architecture_self_test.py  -> 14/14 PASS
  - sqlite3 swarm_memory.db "SELECT COUNT(*) FROM record_links WHERE
      actor='milestone'"  -> count climbs by 3+ per future milestone
  - python3 -c "from scripts.studio_milestone import _extract_refs;
      print(_extract_refs('S-88A6C8C18A and PACKET-07'))"
      -> ({('step','S-88A6C8C18A')}, {'PACKET-07'})

Why this matters:
  This IS the brain Seven is named for. Every piece of work from now
  on auto-deposits its provenance into the graph. After 50 milestones
  the user can ask 'what touched Studio defaults' and Spotlight can
  walk the edges back to find every related milestone, step, and
  proposal. The test bar protects against silent regressions of the
  auto-linker itself.

Step touched: S-88A6C8C18A (tile-click home-vs-tab fix, queued for
the first batch of the surface sweep)."""

res = log_milestone(
    packet="PACKET-08",
    title="Foundation: auto-link milestones + self-test bar to 14 + milestone-kind fix",
    story=STORY,
    status="doing",  # PACKET-08 still has more slices coming.
)
print(json.dumps(res, indent=2))
