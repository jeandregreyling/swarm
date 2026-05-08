"""Slice-5e milestone: Tasker visibility, calendar placement, Agents tile filter+groups."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Three flagged surfaces: Tasker had no home-tile (only reachable
  through the Spotlight or hidden buttons in other tiles), the Tasker
  calendar appeared *below* the new-task header which buried the most
  useful "what's coming up" view, and the Agents tile dumped every
  agent into a single flat list with no quick filter.

What we built:
  - Tasker home tile (frontend/templates/terminal_base.html):
      New home-card after Files: data-win-id=\"tasker\", data-win-template
      =\"view-tasker\". Subtitle: \"Schedule, calendar & watched topics\".
      Window-manager (window-manager.js) and icons.js both got the
      matching clock-glyph SVG so the tile, taskbar pill, and Spotlight
      all show the same icon.

  - Calendar moved up (terminal_base.html, view-tasker template):
      Reordered template blocks so the calendar panel renders
      *immediately under* the stats row, before the search/filter
      header. The first thing the user sees on Tasker is now \"what is
      coming up this week\", not \"how do I make a new task\". The new-
      task header still works the same — just sits below the calendar.

  - Agents tile filter + tier groups (frontend/static/js/views/access.js):
      Slice-5e rewrite of agentsRenderList:
        * Sticky search box at top: \"Filter agents…\" — matches against
          name + label + model + tier in real time. Hides rows that
          don't match; also hides empty group headers.
        * Rows now grouped under sticky tier headers in this order:
          Human → Local → Service → API. Each header shows the count
          for that tier, e.g. \"LOCAL (12)\".
        * Existing click-to-detail behaviour is preserved (data-name
          + delegated listener still fire agentsShowDetail).

How to verify:
  - curl static/js/views/access.js?v=5 / window-manager.js?v=31 → 200.
  - Home grid: new \"Tasker\" tile appears after Files.
  - Click it: opens Tasker; calendar is the first panel under stats.
  - Open Agents: filter input is sticky on top, agents grouped by
    tier with counts; type \"local\" or model name to narrow the list.

Why this matters:
  Tasker was effectively invisible from the home view, which is where
  most navigation starts. Pinning it to the diamond means scheduled
  jobs become a first-class surface like Email or Files. Calendar-
  first inside Tasker matches the user's mental model: this tile is
  about what's happening *next*, not about authoring tasks. The
  Agents filter scales with the roster — filtering 30+ agents by
  typing 3 chars beats scrolling and squinting.

Still open (slice 5f): Studio internals — defaults, proposals
branching, GIT blocks."""

log_milestone(
    packet="PACKET-08",
    title="Tasker home tile + calendar-first layout + Agents filter and tier groups",
    story=STORY,
    status="done",
)
print("ok")
