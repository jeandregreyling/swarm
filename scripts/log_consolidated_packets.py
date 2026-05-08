#!/usr/bin/env python3
"""One-shot logger that adds packet-level architecture improvements
to the consolidated project P-00221285D1 via the live Studio API.

Idempotent: each step uses a stable [PACKET-xx] title prefix; we GET
the project first, skip any title that already exists.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

API = "http://localhost:5050"
PROJECT = "P-00221285D1"


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", "body": e.read().decode("utf-8", "replace")[:300]}


def _get(path: str) -> dict:
    try:
        with urllib.request.urlopen(API + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}


# Packet-level steps. Each becomes one row in P-00221285D1 and is the parent
# epic for related sub-steps (which we keep in their existing rows).
PACKETS = [
    (
        "[PACKET-01] Studio as sole source of truth — loose-doc ingestion + archive",
        "Ingest the 70 loose .md files in repo (docs/, README.md, ops/, runbooks/, "
        "agent personalities/diary/blueprint, swarm_docs/, .instructions.md) into "
        "Studio project_docs and/or library_sources, link to a Studio project, "
        "version snapshot, then move the on-disk originals into Archives/ with a "
        "redirect pointer doc. Acceptance: zero un-tracked .md files outside "
        "Archives/.git/.venv; a Studio search returns every legacy doc by title.",
    ),
    (
        "[PACKET-02] Per-record file model — break monolith state into individual files",
        "Replace the monolithic table-blob model with one canonical file per "
        "record under runtime/records/<kind>/<id>.json (kinds: project, step, "
        "case, run, proposal, ticket, email, note, doc). DB rows become indexes "
        "over the file store. Add a writer that emits both DB row and file, "
        "and a reader that reconciles on boot. Acceptance: every project, step, "
        "case, proposal, ticket, and email exists as a single openable file with "
        "a stable URI; the file is the artifact, the row is the index.",
    ),
    (
        "[PACKET-03] ALM detail surfaces — open step, open case, open run, open proposal",
        "Add proper detail views in projects.js: openStep(step_id), openCase(case_id), "
        "openRun(run_id), openProposal(proposal_id). Each opens a focused panel/window "
        "with description, owner, status timeline, linked evidence (test runs, KC docs, "
        "spine events, artifacts), and inline edit. Backend: GET /api/knowledge/steps/<id>, "
        "/cases/<id>, /runs/<id> returning the full record. Acceptance: clicking any "
        "step/case/run/proposal in Studio opens its full detail without leaving the tile.",
    ),
    (
        "[PACKET-04] Project overview surface — relationships, packets, evidence dashboard",
        "Add a default Overview tab when a project is selected, showing: packet "
        "rollup (status counts per packet), step graph (parent-child), linked "
        "proposals/test-cases/test-runs/notes, KC docs registered against the "
        "project, and recent spine events. Replace the current flat step list as "
        "the landing view. Acceptance: opening P-00221285D1 shows the packet "
        "structure and how everything is related, not a 273-row scroll.",
    ),
    (
        "[PACKET-05] System-runs-in-itself architecture lock — gap audit + gates",
        "Audit the claim that the system can run inside itself end-to-end and "
        "log every gap as a sub-step. Known suspects from this sweep: standalone "
        "/media-center route still serves a raw test template; loose .md outside "
        "Studio; flat backlog with no packet rollup; no openable step/case/run; "
        "swarm.db + studio_proposals.db retirement still pending; thinking_tree "
        "log + landscape generated docs still outside .gitignore in places. "
        "Acceptance: an architecture self-test script lists zero known gaps.",
    ),
    (
        "[PACKET-06] Backlog dedupe + packetization inside P-00221285D1",
        "Tag every existing todo/doing step with its parent packet (PACKET-01..05 "
        "above plus Media Center, Studio Hygiene, Runtime Gateway, Validation). "
        "Archive duplicates that were imported from now-on_hold projects (P-BD5B54E749, "
        "P-10F93B5799, P-1BAD468675, P-441A6D6476) once they map cleanly to a "
        "packet. Acceptance: every open step has exactly one packet tag; "
        "duplicate-imported rows count = 0.",
    ),
    (
        "[PACKET-07] Inter-tile improvement sweep — flagged surfaces beyond Media Center",
        "User flagged that every tile and inter-connected piece has been called "
        "out for improvement, not only Media Center. Confirmed open from this "
        "consolidated project: chat-tile thread row, chat resize dragger, "
        "main-terminal thread dropdown, Studio defaults/proposals branching/GIT "
        "blocks, Vortex section expand+resize+health, Tasker visibility/calendar "
        "placement, agents tile UX, docs/manual UX, spotlight icon compactness, "
        "feeds connectors login, KC interest suggestions, memory↔hive sync, "
        "thought-bubble persistence, local-agent banner cleanup. Each must be "
        "pulled into a packet, not left as flat MD-FEATURE rows.",
    ),
    (
        "[PACKET-08] Separate-file artifact path for tasks/tests/proposals/tickets/emails",
        "Concrete writer/reader implementation for PACKET-02. New module "
        "core/records/store.py exposes save_record(kind, id, data) + load_record. "
        "Storage layout: runtime/records/<kind>/<yyyy>/<mm>/<id>.json. Hooks into "
        "every existing create_* path (projects, steps, cases, work_proposals, "
        "tickets, pending_emails, project_blackboard_notes, project_docs). "
        "Acceptance: deleting the row from DB and re-importing the file restores "
        "the record byte-for-byte.",
    ),
]


def main() -> int:
    proj = _get(f"/api/knowledge/projects/{PROJECT}")
    if not proj.get("ok"):
        print("Could not fetch project:", proj)
        return 1
    existing_titles = {s.get("title", "") for s in proj["project"].get("steps", [])}
    added = 0
    skipped = 0
    for title, desc in PACKETS:
        if title in existing_titles:
            skipped += 1
            print(f"  skip  {title}")
            continue
        r = _post(
            f"/api/knowledge/projects/{PROJECT}/steps",
            {"title": title, "description": desc, "owner": "seven"},
        )
        if r.get("ok"):
            print(f"  add   {title}  -> {r.get('step', {}).get('step_id')}")
            added += 1
        else:
            print(f"  FAIL  {title}  -> {r}")
    print(f"\nPackets: added={added} skipped={skipped}")

    overview = (
        "PROJECT OVERVIEW (2026-05-01 sanity sweep).\n"
        "This is the single consolidated improvement project. Everything we are "
        "building, fixing, or deciding lives here. Packets [PACKET-01..08] above "
        "are the delivery epics; every other todo/doing step belongs under one "
        "of them.\n\n"
        "Architecture truths:\n"
        "  - Studio + Knowledge Center in swarm_memory.db = source of truth.\n"
        "  - Spine (core/spine.py) carries every significant event.\n"
        "  - Vortex shows traceability of changes across the system.\n"
        "  - Records (project/step/case/run/proposal/ticket/email) must each be "
        "openable and exist as their own file (PACKET-02/03/08).\n\n"
        "Known gaps from this sweep:\n"
        "  - 70 loose .md files; only ~5 doc-typed rows in project_docs are "
        "named after on-disk files. The rest of the project_docs rows are "
        "narrative notes, not the live docs. PACKET-01 fixes this.\n"
        "  - projects.js has no openStep / openCase / openRun. PACKET-03 fixes.\n"
        "  - No packet rollup view in Studio Projects tab. PACKET-04 fixes.\n"
        "  - 273 todo / 6 doing / 28 done in this project; many imported "
        "duplicates from on_hold projects. PACKET-06 fixes.\n"
        "  - Standalone /media-center route still serves the raw test template "
        "(frontend/templates/views/media-center.html) instead of the real shell. "
        "PACKET-05 captures.\n\n"
        "Suggested execution order: 01 → 03 → 04 → 06 → 02/08 → 07 → 05. "
        "Reason: ingest first, then make detail/overview visible, then dedupe, "
        "then split monolith, then sweep tiles, then close the architecture gate."
    )
    note = _post(
        f"/api/knowledge/projects/{PROJECT}/blackboard",
        {"kind": "decision", "content": overview, "author": "codex"},
    )
    print("Overview note:", note.get("ok"), note.get("note", {}).get("note_id", note.get("error")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
