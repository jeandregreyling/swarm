"""Log the Platinum-layer milestone narrative into Studio."""
from scripts.studio_milestone import log_milestone

STORY = """\
Goal:
  Make the documentation/linking layer Platinum — every record is a
  file, every relationship is typed, and the system 'just knows' how
  things connect. Tickets can become proposals can become projects;
  threads can morph into tickets; mentions auto-link both ways; nothing
  ever lives only in one DB row.

What we built (this slice, all under core/records/):
  - store.py — file-per-record at runtime/records/<kind>/<yyyy>/<mm>/<id>.{json,md}.
    10 kinds: project / step / case / run / proposal / ticket / email
    / note / doc / thread. Sidecar .md is human-readable (Title / meta /
    Body / Messages-for-thread / Mentions / File-URI). Idempotent saves.
  - links.py — typed-edges DB at runtime/records/_links.db. Auto-inverse
    relationships (promoted_from↔promoted_to, supersedes↔superseded_by,
    blocks↔blocked_by, child_of↔parent_of). neighbours()/outgoing()/
    incoming() helpers.
  - promote.py — record morphing. FIELD_MAP routes ticket→proposal,
    proposal→project, ticket→project, thread→ticket, thread→proposal,
    note→ticket, email→ticket, step→ticket. Discovers real columns via
    PRAGMA table_info so it survives schema drift. Auto-writes a
    promoted_from edge (with auto-inverse promoted_to). promotion_chain()
    walks the lineage in both directions.
  - xref.py — denormalised cross-reference index at runtime/records/
    _xref.json. Extracts mentions (P-, S-, MD-FEATURE-, C-, R-, PR-,
    TKT-, N-, T-, PACKET-NN) from every record body and writes typed
    'mentions'/'mentioned_by' edges in both directions.
  - _ledger.jsonl — append-only audit ledger; every save_record() writes
    one line {ts, actor, kind, id, hash}.

What we built (HTTP):
  Five new endpoints on the records blueprint:
    GET  /api/records/_kinds                    → list of 10 kinds
    GET  /api/records/<kind>?q=                 → list view (capped 500)
    GET  /api/records/<kind>/<id>               → record + sidecar md
                                                  + outgoing/incoming
                                                  links + promotion chain
    POST /api/records/<kind>/<id>/links         → write typed edge
    POST /api/records/<kind>/<id>/promote       → morph to dst kind

What we built (verification):
  Four new invariants in scripts/architecture_self_test.py:
    - Platinum: every record has a .md sidecar
    - Platinum: append-only ledger present
    - Platinum: typed-edges links DB live
    - Platinum: thread kind wired
  CHECKS list now 11 entries. Current run: 11 checks, 11 pass, 0 fail.

Bootstrap counts (after rm -rf runtime/records && snapshot_all && xref.build):
  - 1,681 JSON record files
  - 1,681 .md sidecars
  - 1,681 ledger entries
  - 4,798 typed edges in _links.db
  - 1,372 records mentioned in _xref.json
  - 212 thread records (joined from conversations + messages)
  - kinds: project=35, step=727, case=217, run=183, proposal=16,
           ticket=0 at-snapshot, email=8, note=34, doc=249, thread=212

Live morphing demo (real thread, real DB writes):
  start:    thread   2230  ('gemma: SKILL search python')
    →       ticket   TKT-1D5C56EB06
    →     proposal   PR-E762CBC644
    →      project   P-3E6D8E607C
  promotion_chain(proposal) returned the full lineage in order:
    thread → ticket → proposal → project.
  GET /api/records/proposal/PR-E762CBC644 returns the record, the
  sidecar markdown, links.outgoing (promoted_to project), links.incoming
  (promoted_from ticket, plus auto-inverse from project), and the chain.

How to verify yourself:
  - python3 scripts/architecture_self_test.py     → 11/11 PASS
  - curl -s http://127.0.0.1:5050/api/records/_kinds
  - PYTHONPATH=. python3 scripts/_demo_promote.py
  - find runtime/records -name "*.md" | wc -l     → 1681
  - wc -l < runtime/records/_ledger.jsonl         → 1681
  - sqlite3 runtime/records/_links.db "SELECT COUNT(*) FROM record_links"

Why this matters:
  Every ticket, proposal, project, thread, doc, note, email, step, case,
  and run now lives as a real file the user (or any tool) can grep,
  Spotlight-search, link to via vscode://file/..., or back up to disk.
  The DB is still the index of record, but it is no longer the only
  copy. Relationships are first-class: a ticket promoted from a thread
  carries a typed promoted_from edge with an auto-inverse, so walking
  the matrix in either direction is one indexed lookup. Mentions in
  free text auto-link both ways. This is the foundation for the Records
  tab inside Studio and the Files tile in the knowledge centre — both
  of which can now be built as thin views over the same API.

Still open (will land as separate milestones):
  - Records tab inside Studio (consumes the 5 endpoints above).
  - Files tile in the knowledge centre, anchored at runtime/records/.
  - Mutation hooks: wire save_record() into every create/update path
    in core/knowledge/projects.py and the proposal / ticket / email
    INSERT paths so the on-disk file + ledger always refreshes.
  - Attachments: content-addressed store at runtime/attachments/<sha256>/
    so binary evidence is identified by bytes, not name.
  - Remaining 124 PACKET-07 UX rows (chat-tile thread row, resize
    dragger, terminal thread dropdown, 'Open in Studio' shortcuts,
    Tasker / SAP-watcher tiles).

Closing note: this is the slice the user asked us to embed with the
same gravity as the Diamond layer — Platinum in value. With sidecars
+ ledger + typed edges + morphing + mentions, the swarm now has the
neurological layer that lets it 'just know' how items relate.
"""

log_milestone(
    packet="PACKET-08",
    title="Platinum layer live — file-per-record + .md sidecars + typed edges + morphing",
    status="done",
    story=STORY,
)
print("ok")
