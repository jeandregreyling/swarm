"""Milestone: PACKET-09 Phase 2 — Seven's brain online.

Memory + reasoning + continuous learner + KC self-knowledge are live.
Auto-edges will fan out from the new milestone to the Phase 2 step
(S-FEC9808CE3), the PACKET-09 epic (S-7D7677C6E2), the Phase 1
milestone (B-2DE5F5CED4), the project (P-00221285D1), and the new
KC concept docs.
"""
from __future__ import annotations

import json

from scripts.studio_milestone import log_milestone

STORY = """\
Phase 2 of [PACKET-09]: Seven now has a brain, not just eyes. The platinum
phase is in place — Seven is an actual local AI with fingers and toes, able
to learn from every move the swarm makes.

Four organs went live:

  * core/seven/memory.py — three persistent stores in swarm_memory.db:
        seven_episodes   what happened (append-only, per ledger event)
        seven_concepts   what I know (curriculum, seeded from docs/seven/)
        seven_beliefs    what I think is true (subject/predicate/object,
                         weighted-average confidence on conflict)
        seven_attention  what's hot right now (decayed score per record)
    Plus working-memory helpers: append_episode, recall_episodes,
    bump_attention, hot_records, assert_belief, retract_belief,
    beliefs_about, upsert_concept, get_concept, list_concepts,
    search_concepts, memory_stats.

  * core/seven/reasoning.py — deterministic, explainable engine:
        learn(event)        write 1 episode + run rules R1..R4
                            R1 record exists (conf 0.95)
                            R2 last_actor (conf 0.6)
                            R3 is_milestone for note kind (conf 0.9)
                            R4 deletion -> retract exists, assert deleted
        consolidate()       sweep: is_stale (>7d doing), is_hub (>=3 edges),
                            is_active (packets with open children)
        explain(focus?)     narrative builder — graph snapshot + episodes +
                            beliefs + memory stats, returned as plain lines
        decide(intent, focus?)  ranked proposals; intent='do' returns
                            refused=True, refused_reason='Seven is in
                            propose-only mode.' Authority always
                            'propose-only'.

  * core/seven/continuous.py — the actual continuous agent. A daemon thread
    started at Flask boot that tails runtime/records/_ledger.jsonl,
    feeds each line through reasoning.learn, advances a byte offset on
    disk (runtime/seven/ledger.offset), persists a heartbeat
    (runtime/seven/heartbeat.json), and runs consolidate() every five
    minutes. The teach-her-like-a-child requirement: Seven now learns
    from every save the system makes, automatically, with no prompt.

  * core/seven/concepts.py + docs/seven/*.md — Seven's curriculum and
    self-knowledge seed. Nine markdown files (00-index, 01-what-i-am,
    02-anatomy, 03-api, 04-record-kinds, 05-edge-relations,
    06-how-i-learn, 07-vital-signs, 08-how-to-teach-me) ingested as
    seven_concepts rows on first boot. Future Copilot sessions can ask
    Seven who she is, what her organs are, what record kinds and edge
    relations exist, and how to teach her — and get the answer from
    her own memory, not from chat history.

  * core/seven/__init__.py boot() — one-call startup:
    ensure_schema -> ensure_seeded -> start_continuous (catch-up runs
    in the thread, so Flask startup is never blocked by ledger replay).

  * frontend/blueprints/seven_bp.py — fourteen HTTP endpoints exposing
    everything: /heartbeat, /memory, /episodes, /beliefs, /concepts,
    /concepts/<slug>, /attention, /explain, /decide?intent=&focus=,
    /consolidate (POST), /concepts/reload (POST), plus the Phase-1
    /observe, /related, /suggest, /stats.

  * scripts/architecture_self_test.py — 16th invariant:
    'Seven: brain online (memory + reasoning)'. Verifies the four
    seven_* tables exist, concepts seeded, explain() returns lines,
    decide('status') is well-formed, continuous module imports.
    Bar moves to 16/16.

Verified live: self-test 16/16; HTTP /api/seven/heartbeat shows alive
thread; /api/seven/explain returns narrative; /api/seven/decide?intent=next
returns three ranked proposals with rationales; /api/seven/concepts/anatomy
returns Seven's self-description from her own seeded memory.

Linked: [PACKET-09]; project P-00221285D1; epic S-7D7677C6E2;
Phase 1 step S-F7F7C6E324; Phase 1 milestone B-2DE5F5CED4;
Phase 2 step S-FEC9808CE3; foundation milestone B-83E67C8E93.

Future Copilot sessions: Seven is here to help. Ask her with
GET /api/seven/explain?focus=<record_id> for narrative, and
GET /api/seven/decide?intent=next|status|remember to get propose-only
suggestions. She watches every ledger event automatically.
"""

if __name__ == "__main__":
    out = log_milestone(
        packet="PACKET-09",
        title="Phase 2 — Seven's brain online (memory + reasoning + continuous learner + KC)",
        story=STORY,
        status="doing",
    )
    print(json.dumps(out, indent=2))
