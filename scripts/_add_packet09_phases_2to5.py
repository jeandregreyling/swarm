"""Add Phase 2-5 sub-steps under [PACKET-09] so the project tracks them.

Phase 1 already exists as S-F7F7C6E324 (done). These four are todo and will
inherit child_of edges to the PACKET-09 epic when their milestones land.
"""
from __future__ import annotations

import json

from scripts.studio_milestone import _http

PROJECT = "P-00221285D1"

PHASES = [
    {
        "title": "[PACKET-09] Phase 2 — Seven sparkles in Studio + Records detail panes",
        "description": (
            "Every Studio proposal/step detail and every Records detail view should "
            "fetch /api/seven/related/<kind>/<id>?depth=1 and render a 'Related' "
            "section grouped by relation (mentions, child_of, supersedes, "
            "promoted_from, blocks). Hovering a row shows hop-2 neighbours. "
            "A small sparkle indicator pulses when Seven has fresh suggestions "
            "for the focus record (drives the 'why is this worth my attention' "
            "feedback loop without adding any new tile)."
        ),
        "status": "todo",
    },
    {
        "title": "[PACKET-09] Phase 3 — Seven is default chat target; agents become @addressables",
        "description": (
            "Chat tile and Spotlight chat-route currently dispatch to specific "
            "agents (Duck, Librarian, Gemma, etc.). Reframe: Seven is the default "
            "recipient; when a message starts with @duck, @librarian, @gemma, etc. "
            "the message is forwarded to that named agent muscle. Seven's reply "
            "uses /api/seven/observe to ground answers in the graph (records, "
            "open steps, recent activity) and quotes record IDs so Spotlight "
            "can deep-link from the reply. Propose-only authority: Seven may "
            "*recommend* opening a ticket / logging a milestone / dispatching "
            "to an agent, but does not act unprompted in this phase."
        ),
        "status": "todo",
    },
    {
        "title": "[PACKET-09] Phase 4 — Vortex consumes /api/seven/related for record life-stories",
        "description": (
            "Vortex (Time Wizard) currently shows section health and proposal "
            "history. Add a 'Life of this record' lane: given a focus record, "
            "walk outgoing+incoming edges and render a chronological timeline "
            "of the records that mention/are-mentioned-by/promoted-from/"
            "supersede the focus, sourced from record_links.created_at. "
            "Becomes Seven's memory of its own life on every record."
        ),
        "status": "todo",
    },
    {
        "title": "[PACKET-09] Phase 5 — Diamond + orbs reflect Seven's vitals and suggestion pulses",
        "description": (
            "Diamond home view + the floating orbs should subscribe to "
            "/api/seven/stats (cheap poll, ~30s) and /api/seven/suggest (60s). "
            "Vitals drive the diamond's heartbeat (edge count, open steps, "
            "stale-doing count). Suggestion items drive a soft sparkle on "
            "the orb of whichever surface owns the suggestion's target "
            "(a stale-doing step with a Studio packet pulses the Studio orb). "
            "Click-through routes to Spotlight pre-filled with the target id "
            "so Seven's voice stays consistent across surfaces."
        ),
        "status": "todo",
    },
]


def main() -> None:
    out = []
    for p in PHASES:
        r = _http("POST", f"/api/knowledge/projects/{PROJECT}/steps", p)
        out.append({"title": p["title"][:60] + "…", "result": r})
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
