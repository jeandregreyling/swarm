"""Slice-5c milestone: spotlight compactness + thought-bubble persistence + local-agent banner cleanup."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Tighten three small surfaces that the user kept hitting: the
  Spotlight overlay (rows felt big and bouncy), the orb thought
  bubbles (always blank for 20-50s after a reload), and the agent
  edit screen's local-runtime status block (was a chunky banner that
  didn't read at a glance).

What we built:
  - Spotlight overlay (frontend/templates/terminal_base.html):
      * Section header padding 8/18/4 -> 6/14/3, font 10 -> 9.5px.
      * Item padding 9/18 -> 7/14, gap 12 -> 10.
      * Item icon 28x28 -> 22x22, radius 7 -> 5, font 14 -> 12.
      * Item title 13 -> 12.5px, sub 11 -> 10.5px.
      Net effect: ~25% denser list, more results visible without
      scrolling, no behaviour changes.

  - Orb thought-bubble persistence (frontend/static/js/views/orbs.js):
      * New _persistThought(o) writes the orb's thought to localStorage
        under fridays-orb-thoughts-v1, keyed by role, with a Date.now()
        stamp. Persisted only once a thought reaches 'hold' (so we never
        save mid-fade noise).
      * New _hydrateThoughts() reads at startup (700ms after load,
        after orbs settle), and for any orb whose persisted thought is
        less than 5 minutes old it re-shows the bubble in 'hold' phase
        for ~4s, then fades naturally.
      * Cooldown for the next natural thought is shortened to 8-18s
        post-hydration so the page never feels frozen.

  - Local-agent banner cleanup (frontend/static/js/views/access.js):
      * Replaced the multi-line red banner blocks ("Local agent
        unavailable: Ollama is offline." + paragraph + button) with a
        single-row pill: status dot + label + small "Local AI ->" link.
      * Same visual rule for "model not installed" and "ready" states.
      * Now reads as a status line, not an interruption.

How to verify:
  - curl orbs.js?v=36 / access.js?v=4 -> both 200.
  - Open Spotlight (Ctrl+Space): rows are tighter, more visible.
  - Open an orb (let it bubble), reload page: bubble appears within 1s.
  - Edit an agent in Access tile: ready/offline/model state shows as
    a single-line dot+label, not a paragraph.

Why this matters:
  Three small UI rough edges that user kept calling out. Spotlight is
  now scannable in one glance, orbs feel alive immediately on reload
  (instead of "did the brain die?"), and agent runtime status is a
  glanceable indicator instead of a wall of red text.

Still open (slices 5d-5f): Vortex section expand+resize+health,
Tasker/calendar/agents tile UX, Studio defaults/proposals/GIT blocks."""

log_milestone(
    packet="PACKET-08",
    title="Spotlight density + thought-bubble persistence + local-agent status pill",
    story=STORY,
    status="done",
)
print("ok")
