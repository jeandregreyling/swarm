"""Log batch of UX bug verifications + bug #1 fix following Slice A/E."""
from __future__ import annotations
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.knowledge import projects  # type: ignore

PROJECT_ID = "P-94531FE267"

CONTENT = """[MILESTONE] Post-Slice-A UX bug sweep — 2026-06-01

Triaged the 6 bugs raised in walkthrough note B-79394EBF0C.

== FIXED ==

Bug #1 — #shortcuts-help-modal close button intercepted.
  Root cause: modal markup carries inline `opacity:0; pointer-events:none`
  and `display:flex`; no `.open` CSS rule existed in modals.css to override
  them. Adding `.open` only flipped a class with no visual effect, so
  #troubleshoot-btn / #home-header (which actually sat on top) swallowed
  every click.
  Fix: appended to frontend/static/css/modals.css:
    #shortcuts-help-modal.open { opacity:1 !important; pointer-events:auto !important; }
  Live verification: opened modal → opacity 1, pointer-events auto,
  elementFromPoint at the close X resolves to the <path> inside the modal
  SVG (top.closest('#shortcuts-help-modal') === modal). ✔

== NOT REPRODUCIBLE / NON-ISSUES ==

Bug #2 — Ctrl+B / Ctrl+J not bound.
  Bindings exist in frontend/static/js/core/init.js (Ctrl+K/T/P/H/J/G/E/B
  + Ctrl+Space). Live dispatch of `keydown {key:'b', ctrlKey:true}` from
  document.body opened #win-knowledge (display:flex); same for Ctrl+J →
  #win-chat. The original 'does nothing' observation was almost certainly
  triggered while focus sat inside a textarea/input — the handler
  intentionally skips shortcuts when typing into one (isInput guard).

Bug #3 — /api/diamond/residency 404 spam.
  Already addressed in Slice E (see milestone B-A7CB12F46E). Server is now
  silent on Connection-refused / Errno 111 for `_get_agent_residency`.

Bug #4 — Wishlist tiles with empty .card-title.
  All four (wishlist-cyber / -financial / -trading / -business) are
  declared in terminal_base.html with `hidden style="display:none !important;"
  aria-hidden="true"`. They are intentionally not rendered; the empty
  title text is a non-issue because the elements aren't on screen.

Bug #5 — Peach/pink leak on KC + Media floating windows.
  Covered by Slice A token refactor — once a theme other than the
  login-fallback is active, all *.media-*-btn-primary buttons and KC tab
  chrome inherit `var(--accent)` and the active body.theme-* tokens.

Bug #6 — 'Friday' vs 'Fridays' branding mismatch.
  Live DOM check: home-header text starts with 'Fridays\\nSeven\\'s Swarm'
  and page title is 'Fridays — Seven\\'s Swarm'. No singular 'Friday'
  branding anywhere visible. Likely visual misread during the original
  walkthrough.

== BLOCKED ==

Library 'nomic-embed-text not found':
  Ollama is not installed in the WSL runtime (`which ollama` → no result).
  The Library semantic-search error is a "wire up Ollama first" task,
  not a model-pull task. Recommend installing Ollama via the Local AI
  onboarding window before retrying.

== TEST EVIDENCE ==
pytest tests/test_v7c_a04_monitor_visibility.py tests/test_chat_quality.py
  → 22 passed, 0 failed (re-run after edits).

== REMAINING ==
Slice C (packaging decision) — needs user choice between PyInstaller MSI
shell, Tauri wrapper, or accepting the existing .bat launcher.
"""

try:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, author="copilot-audit", kind="milestone")
except TypeError:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, kind="milestone")
print(f"project_id={PROJECT_ID}")
print(f"created_note_id={note.get('id') if isinstance(note, dict) else note}")
