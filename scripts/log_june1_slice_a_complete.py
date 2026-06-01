"""Log Slice A (theme/sundial token refactor) + Slice E (residency probe guard) completion."""
from __future__ import annotations
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.knowledge import projects  # type: ignore

PROJECT_ID = "P-94531FE267"

CONTENT = """[MILESTONE] Slice A (theme/sundial token refactor) + Slice E (residency probe guard) — 2026-06-01

== SLICE A — Theme + Sundial token refactor ==
Goal: eliminate hardcoded health/info hex colors and rebuild theme picker as class-based.

Files changed:
  - frontend/static/css/core.css         : added :root health tokens
      --health-ok/warn/crit, *-rgb triplets, --info, --info-rgb
  - frontend/static/css/diamond.css      : full token sweep
      .sundial-ray.ray-{ok,warn,crit}, #sundial-title[data-health],
      @keyframes sundial-rage + sundial-throb, .sundial-node[data-health],
      .stip-h-{ok,warn,crit} .stip-dot, .attn-dot-{info,warn,crit},
      .ctx-danger:hover all converted to var(--health-*) / rgba(var(--*-rgb), α).
      #sundial-center got max-width:92px + pointer-events:none to fix
      title/sub overlap with orbital rays.
  - frontend/static/css/taskbar.css      : new picker classes
      .theme-picker-heading / -sep / -item (with [data-active="1"] state)
      / .theme-swatch — replaced the old inline-style buttons.
  - frontend/templates/terminal_base.html: rebuilt theme picker menu
      22 entries (auto + 21 NAMED_THEMES) using .theme-picker-item + swatches
      + 4 .theme-picker-sep groupings.
  - frontend/static/js/core/theme.js     : _applyNamedTheme(name) now toggles
      data-active="1" on the matching .theme-picker-item so the active row
      highlights without inline JS styling.

Live verification (signed in as jeandre, /ui reloaded after server restart):
  - menu.querySelectorAll('.theme-picker-item').length === 22 ✔
  - .theme-picker-heading × 1, .theme-picker-sep × 4, .theme-swatch × 22 ✔
  - window.setNamedTheme('cyber') → body.className "mode-light theme-cyber",
    data-active="1" lands on the cyber entry ✔
  - #sundial-center computed maxWidth 92px, pointerEvents none ✔
  - title rect 54×20 at (64,74) inside the 92px center; no longer spilling rays ✔

== SLICE E — /api/diamond/residency probe guard ==
File: frontend/blueprints/diamond.py — _get_agent_residency() exception handler
classifies the error: any `str(exc)` containing "Connection refused" /
"Errno 111" / "Max retries" / "NewConnectionError" is downgraded to
logger.debug; all other exceptions still logger.warning. Return shape
unchanged ({'ram': [], 'swap': [], 'gpu': []}).

Live verification: server restarted on :5050; 60+ seconds of /api/diamond/pulse
traffic produced ZERO "[Diamond] residency:" warnings in stderr while Ollama
remained unreachable. ✔

== STATE LINKAGE ==
Closes the unblocker portion of:
  - S-F7C134D9C6 (Tile-Sweep KC)
  - S-1B90B67986 (Tile-Sweep Media)
  - S-BAAE9C22D8 (Tile-Sweep general)

== TEST EVIDENCE ==
pytest tests/test_v7c_a04_monitor_visibility.py tests/test_chat_quality.py
  → 22 passed, 0 failed.

== ASSET CACHE-BUST ==
terminal_base.html bumped:
  core.css?v={{ASSET_VERSION}}, themes.css?v={{ASSET_VERSION}},
  taskbar.css?v=31-themepicker, theme.js?v={{ASSET_VERSION}}-picker21.

== REMAINING ==
Slice B (picker rebuild) effectively delivered as side-effect of Slice A
markup work — needs only user sign-off.
Pending: Slice C (packaging choice), Slice D (KC/Media detail pass),
bugs #1/#2/#4 from walkthrough note B-79394EBF0C, pull nomic-embed-text
in Ollama for Library semantic search.
"""

try:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, author="copilot-audit", kind="milestone")
except TypeError:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, kind="milestone")
print(f"project_id={PROJECT_ID}")
print(f"created_note_id={note.get('id') if isinstance(note, dict) else note}")
