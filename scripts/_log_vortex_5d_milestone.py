"""Slice-5d milestone: Vortex tile — collapsible sections, resizable history, health pill."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Vortex was rigid: the right-hand history rail had a fixed width,
  the Vortex History and Spine Feed sections couldn't be hidden when
  you wanted more room for the timeline, and there was no glanceable
  signal that Vortex was actually healthy (live session, checkpoints
  saved, events flowing). User asked for expand+resize+health.

What we built:
  - Health pill (frontend/templates/terminal_base.html + time-wizard.js):
      New #tw-health-strip line under the Vortex header. Renders a
      coloured pill with a status dot and one-line summary:
        ok    "Vortex healthy · N sessions · M checkpoints · K events"
        warn  "Vortex live · N events · 0 checkpoints (save one to enable rollback)"
        warn  "Vortex history present · M checkpoints · session inactive"
        idle  "Vortex idle — no sessions or checkpoints yet"
      Re-evaluated every time renderTwSummary() runs (loadTimeWizardData
      + the 15s auto-refresh tick already wired in).

  - Collapsible side sections (terminal_base.html + time-wizard.js):
      Vortex History and Spine Feed headers are now real <button>s
      with .tw-section-toggle + a rotating caret. State persists in
      localStorage 'vortex_section_collapsed' so collapsed stays
      collapsed across reloads. aria-expanded is updated for screen
      readers.

  - Resizable history rail (terminal_base.html + time-wizard.js):
      New #tw-history-resizer separator (role=separator, tabindex=0,
      aria-label, accent on hover/drag). Mouse + touch drag support;
      width clamped to [220px, 60% of window]. Double-click clears the
      saved width back to stylesheet default. Keyboard:
        ArrowLeft / ArrowRight = ±24px
        Home                   = reset
      Width persists in localStorage 'vortex_history_width'.

How to verify:
  - curl static/js/views/time-wizard.js?v=30 -> 200.
  - Open Vortex tile: see green/amber/grey pill under header.
  - Click "Vortex History" header: section collapses; reload, still collapsed.
  - Drag the divider between timeline and history: history pane resizes.
  - Tab to the divider, press ArrowLeft/Right/Home: width adjusts.

Why this matters:
  Vortex is the swarm's traceability surface — when it has a million
  things in it (which it does: 4816 typed edges, 1694 ledger entries
  this session), the user needs to be able to give the timeline more
  room or hide the rail entirely without leaving the tile, and they
  need a one-line "yes, it's running" signal so they don't have to
  manually parse Sessions/Events/Checkpoints/Decisions counts.

Still open (slices 5e–5f): Tasker visibility + calendar + agents tile
UX, Studio defaults / proposals branching / GIT blocks."""

log_milestone(
    packet="PACKET-08",
    title="Vortex tile — health pill, collapsible sections, resizable history rail",
    story=STORY,
    status="done",
)
print("ok")
