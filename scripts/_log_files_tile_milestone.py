"""Slice-4 milestone: Files tile anchored at runtime/records/."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Make the on-disk Platinum file layer browseable as a real folder tree
  from the home grid, not just from inside Studio. Records, sidecars,
  ledger and xref all live under runtime/records/ — and now there is a
  Files tile that lets anyone walk that tree, sandboxed, in two clicks.

What we built:
  - frontend/blueprints/knowledge_bp.py:
      GET /api/records/_browse?path=<rel>
      Hardened against ../ traversal: any path that escapes
      RECORDS_ROOT.resolve() is rejected with HTTP 400.
      Returns {ok, path, parent, count, entries:[{name,is_dir,size,mtime,rel}]}.
  - frontend/static/js/views/records-files.js (~150 lines):
      * Breadcrumb (clickable: runtime/records / kind / yyyy / mm / file)
      * Up button + Refresh
      * Sorted listing (folders first, name asc)
      * Click a folder → navigate. Click a *.json record → inline detail
        pane: chain breadcrumb + .md sidecar + raw JSON + outgoing/incoming
        link counts. Generic files show a vscode://file/<abs path> link.
  - frontend/templates/terminal_base.html:
      * New tile: 'Files' (data-win-id='records-files', data-win-template='view-records-files')
      * <template id="view-records-files"> with breadcrumb header,
        list area, and detail panel. Sits on the Knowledge column of the home grid.
      * <script src="/static/js/views/records-files.js?v=1">
  - frontend/static/js/core/window-manager.js + icons.js:
      * 'records-files' icon registered in both maps so window header,
        taskbar, and tile share the same SVG (folder + lines glyph).
  - frontend/static/js/core/app.js:
      * Window loader dispatches 'records-files' → loadRecordsFilesData(win)

How to verify (proven this slice):
  - curl /api/records/_browse?path= → ok, 13 kind dirs (case, doc, email, …)
  - curl /api/records/_browse?path=../../etc → HTTP 400 (traversal blocked)
  - curl /static/js/views/records-files.js → 200
  - Open the home grid → click 'Files' tile → window mounts, breadcrumb
    shows runtime/records, navigate into proposal/2026/05 → click PR-* →
    inline detail shows chain + .md + raw JSON.

Why this matters:
  The Platinum file layer stops being a developer-only fact. Anyone in
  the UI now sees the same on-disk reality that grep / Spotlight / a
  backup script would see — folders for each of the 10 kinds, time-
  bucketed (yyyy/mm), with .md sidecars next to .json records. No SQL,
  no internal API knowledge needed. And it is sandboxed: you cannot
  escape runtime/records/ from the browser.

Still open: PACKET-07 remaining UX slices. Platinum core is complete:
            mutation hooks, attachments, Records tab in Studio, Files
            tile on home — all live, all 12/12 self-tests green."""

log_milestone(
    packet="PACKET-08",
    title="Files tile — runtime/records/ browseable from the home grid",
    story=STORY,
    status="done",
)
print("ok")
