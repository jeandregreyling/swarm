"""Slice-3 milestone: Records tab inside Studio."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Make the 10-kind Platinum record layer browseable from inside Studio,
  not just via curl. Every kind, every record, every link, every
  promotion chain — visible without leaving the UI.

What we built:
  - frontend/static/js/views/studio-records.js (~290 lines):
      * Kind dropdown (project/step/case/run/proposal/ticket/email/note/doc/thread)
      * Live search (debounced) over title + id
      * 2-pane detail view: rendered .md sidecar (left) + links + raw JSON (right)
      * Promotion chain renders as a one-line breadcrumb at the top of detail
      * Outgoing/incoming links are clickable — jump to that record's detail
      * Toolbar buttons: Promote… (asks for dst kind), Add link…, Open file
        (vscode://file/<abs path>)
  - frontend/templates/terminal_base.html:
      * New 'Records' sub-tab button in the Studio header (between Test Lab and the like)
      * #studio-records-panel anchor below #studio-projects-panel
      * <script src="/static/js/views/studio-records.js?v=1">
      * studio.js bumped to v=33 so old caches don't mask the new sub-tab
  - frontend/static/js/views/studio.js:
      * studioSetTab() learns 'records'; styles the new button + toggles the panel
        and lazy-calls window.loadStudioRecordsPanel()

Backend already had:
  GET  /api/records/_kinds
  GET  /api/records/<kind>?q=
  GET  /api/records/<kind>/<id>
  POST /api/records/<kind>/<id>/links
  POST /api/records/<kind>/<id>/promote

How to verify:
  1. Open Studio → click 'Records' sub-tab.
  2. Pick kind=proposal, search 'Demo Proposal — promotion chain test'.
  3. Click PR-E762CBC644 → detail pane shows the chain
       thread/2230 → ticket/TKT-1D5C56EB06 → proposal/PR-E762CBC644 → project/P-3E6D8E607C
     plus outgoing/incoming links and the on-disk markdown.
  4. Click any incoming link — pane refreshes to that record.
  5. Server log: GET /static/js/views/studio-records.js → 200.

Why this matters:
  The file layer stops being a developer-only curiosity. Anyone in the
  UI can now walk the same chain Spotlight or grep would, see the
  promotion lineage, follow links, and open the underlying sidecar
  directly in VS Code — without writing a single SQL query.

Still open: Files tile (browser-style filesystem view of runtime/records/),
            PACKET-07 remaining UX slices."""

log_milestone(
    packet="PACKET-08",
    title="Records tab inside Studio — universal viewer for all 10 kinds",
    story=STORY,
    status="done",
)
print("ok")
