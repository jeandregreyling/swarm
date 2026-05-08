"""Slice-5b milestone: chat-tile thread row + resize handle + dropdown polish."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Fix three chat surfaces that were called out for friction:
  the home chat thread dropdown (no timestamps, hard to scan),
  the chat resize dragger (mouse-only, no reset, no keyboard),
  and the main-terminal chat thread dropdown (long titles overflowed
  with no tooltip, no truncation, ugly options).

What we built:
  - frontend/static/js/views/home-chat.js (_hcRenderThreadSelect):
      Each option now reads "#<id> · <title> · <DD/MM HH:mm>". Title
      truncated to 44 chars to keep the dropdown narrow. Falls back
      gracefully when timestamps are missing.

  - frontend/templates/terminal_base.html + diamond.js + home-chat.css:
      Resize handle is now a real semantic separator:
        * role="separator", aria-orientation="horizontal", tabindex=0
          so screen readers and keyboard users see it.
        * Touch (touchstart/touchmove/touchend) parity with mouse drag.
        * Double-click clears the saved height (back to stylesheet default).
        * Keyboard: Up/Down nudges 24px, PageUp/PageDown 96px, Home resets.
        * 'home-chat-resizer-active' class brightens the bar while dragging.
        * :focus-visible outline so Tab navigation reveals it.
      The drag math itself is unchanged (still respects handle-above
      vs handle-below mode), so behaviour for existing users is intact.

  - frontend/static/js/views/chat.js (refreshChatThreadList):
      Long titles in the main-terminal dropdown now truncate at 47
      chars + "…", and each option's `title` attribute carries the full
      raw title + timestamp so hover gives the full string back.

How to verify (proven this slice):
  - curl -o /dev/null -w 200s on home-chat.js, diamond.js, chat.js,
    home-chat.css.
  - Open home tile → thread dropdown shows "#NNN · title · 21/05 14:32".
  - Tab to the resize handle → outline appears, ↑/↓ keys nudge,
    Home key resets. Double-click resets via mouse.
  - Open main chat → dropdown options are short; hover reveals full title.

Why this matters:
  Chat is the entry point for everything else. Three rough edges per
  user-flagged: hard to find a thread by date (no timestamp), hard to
  reset the resize after over-dragging, hard to read truncated titles.
  All three are now polished without changing core behaviour.

Still open (slice 5c–5f): spotlight icon compactness, local-agent
banner cleanup, thought-bubble persistence, Vortex expand/resize/health,
Tasker/calendar/agents UX, Studio defaults/proposals/GIT blocks."""

log_milestone(
    packet="PACKET-08",
    title="Chat tile UX — thread rows + resize dragger + main dropdown polish",
    story=STORY,
    status="done",
)
print("ok")
