"""Slice-5a milestone: inter-tile wiring for Records/Files shortcuts."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Make the new Platinum surfaces (Studio Records tab + Files tile) the
  natural next click from the tiles people already use. No more hunting
  through file paths or asking 'which tab again?' — every chat thread,
  ticket, and proposal carries a one-click jump to its record and to its
  on-disk folder.

What we built:
  - frontend/static/js/core/record-shortcuts.js (new):
      window.openRecord(kind, id)     — opens Studio, switches to Records
                                        tab, selects the record. Polls
                                        for the loader so it works even
                                        if Studio is mounting cold.
      window.revealInFiles(kind, id)  — opens the Files tile and navigates
                                        the breadcrumb into runtime/records/<kind>/.
  - frontend/static/js/views/studio-records.js: now exposes
      window.studioRecordsSelect(kind, id) — the entry point used by
      openRecord(). Sets the kind dropdown, runs the list query, and
      jumps the detail pane to the requested record.
  - frontend/static/js/views/records-files.js: now exposes
      window.recordsFilesNavigate(relPath) — used by revealInFiles().
  - Buttons added in three tiles (consistent 'In Records' + 'In Files'
    pair next to the existing badges):
      conversations.js  — chat-thread detail toolbar
      studio.js         — proposal detail header
      studio.js         — ticket detail header
  - terminal_base.html: record-shortcuts.js loaded once in the core
    script block, before any view that uses it. studio.js bumped to v=34;
    studio-records.js + records-files.js bumped to v=2.

How to verify (proven this slice):
  - curl /static/js/core/record-shortcuts.js → 200
  - curl /static/js/views/{studio,studio-records,records-files,conversations}.js
    → all 200 with the new helpers visible.
  - Open a conversation → click 'In Records' → Studio opens, Records tab
    active, kind=thread, the conversation row preselected.
  - Open a proposal → click 'In Files' → Files tile mounts, breadcrumb
    inside runtime/records/proposal/.

Why this matters:
  Until now the Platinum layer was a parallel surface — present, but
  disconnected from day-to-day tiles. Two buttons turn it into the
  default audit path. Users discover the file model through the chat
  and ticket flows they already use, instead of having to learn a new
  tile.

Still open:
  - Apply same pair to project rows + email tickets (next pass).
  - Slices 5b–5f: chat tile UX, spotlight/banner/thought-bubble cleanup,
    Vortex expand/resize/health, Tasker/calendar/agents UX, Studio
    defaults / proposals branching / GIT blocks."""

log_milestone(
    packet="PACKET-08",
    title="Inter-tile shortcuts — 'In Records' + 'In Files' from chats, tickets, proposals",
    story=STORY,
    status="done",
)
print("ok")
