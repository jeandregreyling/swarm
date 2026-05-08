"""Add tile-click → focus existing taskbar tab improvement under PACKET-07."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.knowledge.projects import add_step

sid = add_step(
    'P-00221285D1',
    '[PACKET-07] Home tile click should focus existing taskbar tab, not spawn duplicate window',
    description=(
        "User flagged: clicking a home-grid tile (e.g. Studio) currently opens a "
        "fresh full-window section while the corresponding taskbar tab pill is still "
        "visible. Expected: clicking the tile should focus/restore the EXISTING "
        "taskbar tab for that view (Studio tile -> Studio tab) rather than create a "
        "duplicate or stack a new window over the page.\n\n"
        "Acceptance criteria:\n"
        "  - Clicking a home-tile whose data-win-id is already open in the taskbar "
        "    focuses that window instead of creating a second one.\n"
        "  - Tile click should restore minimised windows.\n"
        "  - Visual cleanup: no leftover full-bleed page-section under an already "
        "    windowed tile.\n"
        "  - Applies to all home tiles: Studio, Files, Tasker, Email, Spotlight, "
        "    Records, Vortex, Diamond, Agents, Media, etc.\n\n"
        "Likely surface: frontend/static/js/core/window-manager.js openWindow() and "
        "the home-card click handler in terminal_base.html / app.js. Probably needs "
        "an early-return path when a window with that win-id already exists -> "
        "focusWindow(id) instead of createWindow."
    ),
)
print('step_id:', sid)
