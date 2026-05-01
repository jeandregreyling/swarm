#!/usr/bin/env python3
"""One-shot: backfill the three milestones already shipped in this session
(media-center route fix, PACKET-01 ingest, PACKET-03 detail surfaces) into
P-00221285D1 as readable blackboard notes + step status updates.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.studio_milestone import log_milestone  # noqa: E402


# ── 1. /media-center route regression fix ───────────────────────────────
log_milestone(
    packet="PACKET-05",
    title="Media Center URL no longer serves a raw test page",
    status="doing",
    story=(
        "What was wrong:\n"
        "  Visiting /media-center on the swarm web UI rendered a 13-line\n"
        "  'Raw HTML Test' placeholder template — that file was left over\n"
        "  from earlier debugging and had been quietly serving instead of\n"
        "  the real Media Center window. The icon was tracked but the URL\n"
        "  was wrong.\n\n"
        "What we changed:\n"
        "  1. Deleted the dedicated /media-center route in\n"
        "     frontend/terminal.py.\n"
        "  2. Folded /media-center into the same convenience-redirect\n"
        "     handler used by /library, /studio, /chat, /monitor. Every\n"
        "     one of those URLs now 302-redirects to /ui#<tile>, so the\n"
        "     master shell template (terminal_base.html) loads and the\n"
        "     window-manager auto-opens the Media Center tile.\n"
        "  3. Archived the broken placeholder template to\n"
        "     Archives/dead_templates_20260501/media-center.raw-test.html\n"
        "     so it cannot accidentally be served again.\n\n"
        "How to verify:\n"
        "  curl -sI http://localhost:5050/media-center\n"
        "    -> HTTP/1.0 302 FOUND  (redirect target /ui#media-center)\n"
        "  Open the URL in a browser and the real Media Center window\n"
        "  shell opens with the transport bar, project rack, structure\n"
        "  dock, editor stage and research tabs — not a raw test page.\n\n"
        "Why this matters for the architecture lock (PACKET-05):\n"
        "  This was the first concrete proof that the system is supposed\n"
        "  to run inside itself but a stale top-level template was leaking\n"
        "  out. Closing this gap is one of the items the PACKET-05 self-\n"
        "  test will keep watch on going forward."
    ),
)


# ── 2. PACKET-01: loose .md ingest + archive ────────────────────────────
log_milestone(
    packet="PACKET-01",
    title="69 loose markdown docs ingested into Studio, 45 originals archived",
    status="done",
    story=(
        "Goal:\n"
        "  Make Studio (the swarm_memory.db project_docs registry) the\n"
        "  single source of truth for documentation. Before today, 70\n"
        "  markdown files lived loose on disk, outside any Studio project,\n"
        "  with only a handful of their contents reflected in project_docs\n"
        "  as narrative notes. That is the exact monolith-vs-source-of-\n"
        "  truth gap PACKET-01 was created to close.\n\n"
        "What we did:\n"
        "  1. Inventoried every .md file in the repo, excluding .git,\n"
        "     .venv, Archives, .history, sandpits and the vendored\n"
        "     llama.cpp tree. 70 files in total.\n"
        "  2. Split them into two pools:\n"
        "       INDEX_ONLY (24 files): runtime files we want tracked but\n"
        "         must stay on disk — agent personalities, Seven's\n"
        "         BLUEPRINT.md and diary.md, model README files, sandpit\n"
        "         readmes. These now exist in project_docs but are NOT\n"
        "         moved.\n"
        "       INGEST_AND_ARCHIVE (45 files): real docs that belong in\n"
        "         Studio — README.md, .instructions.md, the entire docs/\n"
        "         tree (core, audits, runbooks, registry, reference,\n"
        "         testing, api, archive subfolders), ops/, swarm_docs/,\n"
        "         windows/, desktop/.\n"
        "  3. For every file we did:\n"
        "       - INSERT or UPDATE into project_docs (doc_name = the\n"
        "         repo-relative path, so 'docs/CODING_BIBLE.md' becomes\n"
        "         a stable, searchable doc_name).\n"
        "       - Wrote a row into project_doc_versions so the snapshot\n"
        "         is preserved even if the doc is later rewritten.\n"
        "       - Tagged with 'P-00221285D1,sweep-202605-01,ingested,\n"
        "         <category>' so Spotlight + KC search find them.\n"
        "  4. For the 45 INGEST_AND_ARCHIVE files we then physically\n"
        "     moved the original to\n"
        "     Archives/ingested_md_20260501/<original-relative-path>\n"
        "     and replaced the on-disk original with a 4-line redirect\n"
        "     pointer telling future readers (and me) to look in Studio,\n"
        "     not on disk, for the live version.\n"
        "  5. Wrote a manifest at\n"
        "     Archives/ingested_md_20260501/MANIFEST.json containing the\n"
        "     sha256, size, action, category and archive_path of every\n"
        "     file we touched.\n\n"
        "Numbers:\n"
        "  index-only registered:        24\n"
        "  ingest+archive registered:    45\n"
        "  newly created project_docs:   69\n"
        "  physically archived:          45\n"
        "  project_docs total before:   180\n"
        "  project_docs total after:    249\n\n"
        "Reusable tool:\n"
        "  scripts/ingest_loose_md.py  (idempotent — re-running it on a\n"
        "  fresh batch of loose .md files just writes new versions and\n"
        "  archives the new originals; same-content files become a\n"
        "  no-op 'skip-same' line).\n\n"
        "How to verify in Studio:\n"
        "  Open Studio → Knowledge Center, search for 'CODING_BIBLE' or\n"
        "  'ARCHITECTURE' or '.instructions' — the live doc opens from\n"
        "  the database. The on-disk path now contains only the redirect\n"
        "  pointer. The archived snapshot lives at\n"
        "  Archives/ingested_md_20260501/<path>.\n\n"
        "Spotlight hint:\n"
        "  Future-me typing 'where did we put the markdown files' or\n"
        "  'sweep 2026-05-01' or 'PACKET-01' will land on this note."
    ),
)


# ── 3. PACKET-03: ALM detail surfaces ───────────────────────────────────
log_milestone(
    packet="PACKET-03",
    title="Steps and test cases are now openable as full ALM records",
    status="done",
    story=(
        "Goal:\n"
        "  Until today, clicking a step or a test case in Studio gave\n"
        "  you only the inline rename/delete buttons — no way to open\n"
        "  the full record, see its description, parent, linked test\n"
        "  cases, or recent test runs. That broke the ALM contract:\n"
        "  every artifact must be openable.\n\n"
        "Backend (core/knowledge/projects.py):\n"
        "  Added two new functions:\n"
        "    - get_step(step_id)      returns the step row plus its\n"
        "                             linked test_cases list and the\n"
        "                             last 25 test_runs.\n"
        "    - get_test_case(case_id) returns the case row plus its\n"
        "                             parent step (if any) and the\n"
        "                             last 25 test_runs.\n\n"
        "API (frontend/blueprints/knowledge_bp.py):\n"
        "  New routes (Studio JSON API):\n"
        "    GET /api/knowledge/steps/<step_id>\n"
        "    GET /api/knowledge/cases/<case_id>\n"
        "  Both return {ok, step|case} with the nested arrays.\n\n"
        "Frontend (frontend/static/js/views/projects.js):\n"
        "  - Every step row now has a ⤢ Open button (in front of the\n"
        "    existing ▶ ✓ ✎ 🗑 buttons).\n"
        "  - Every test-case row now has a ⤢ Open button.\n"
        "  - New global helpers projectsOpenStep(stepId) and\n"
        "    projectsOpenCase(caseId) build a focused modal showing:\n"
        "      title, id, project, status, owner, ordering, created/\n"
        "      updated timestamps, full description, linked test cases\n"
        "      (clickable through to their own detail), and recent test\n"
        "      runs (each with an Open Run button that hands off to the\n"
        "      Test Lab run inspector).\n"
        "  - Cases also get a ↶ Open parent step button so the\n"
        "    hierarchy can be walked both directions.\n\n"
        "How to verify:\n"
        "  curl http://localhost:5050/api/knowledge/steps/S-22C2B68BB2\n"
        "  Should return JSON with description, status, test_cases[],\n"
        "  test_runs[].\n"
        "  In the UI: Studio → Projects → P-00221285D1 → click ⤢ on\n"
        "  any [PACKET-XX] step.\n\n"
        "Notes:\n"
        "  - Test runs are pulled from the existing test_runs table by\n"
        "    step_id / case_id, so historical runs already attribute\n"
        "    automatically once a project_id is set in Test Lab.\n"
        "  - Future scope (still open under PACKET-03): a similar\n"
        "    detail surface for proposals (work_proposals) and runs\n"
        "    (test_runs) — runs already have testLabOpenRun(), so the\n"
        "    next slice is just proposals."
    ),
)
print("backfill milestones logged")
