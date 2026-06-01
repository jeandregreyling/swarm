"""Log live KC + Media Center walkthrough findings to Studio."""
from __future__ import annotations
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.knowledge import projects  # type: ignore

PROJECT_ID = "P-94531FE267"

CONTENT = """[AUDIT] Live KC + Media Center walkthrough — 2026-06-01 (signed in as jeandre)

== KNOWLEDGE CENTER (#win-knowledge) — all 8 tabs render ==
- Files       : workspace tree visible (~18KB content). OK.
- Docs        : "ALM enforced · Pending 31 · Executed 1". Sub-tabs Workspace/Ghost Brief/Pinboard/ALM History. OK.
- Evidence    : counters live — 638 chunks, 33 rows, 49 sources, 77 docs, 1931 steps, 2 test artifacts, 2 runs, 398 proposals. OK.
- Sources     : 49 sources / 638 chunks across Fridays(20) / SAP Corner(14) / Programming(3) / General(12). OK.
- Memory      : 400/400 entries with per-agent filter. OK.
- Library     : 49 sources · 638 chunks · 12 pdf · 37 text. **WARN: "nomic-embed-text not found" — semantic search disabled.** Pull model in Ollama.
- Tasker      : 19 total · 19 active · 0 disabled · last fired 11d ago. Calendar OK but stale.
- Guide       : Welcome to Fridays + 8-section sidebar (Agents/Chat/KC/Studio/Files/Shortcuts/Settings). OK.

== MEDIA CENTER (#win-media-center) ==
- Structure rendered: stages "1 Pick project / 2 Add reference / 3 Make preview / 4 Play output".
- Counters: 1 projects · 0 queued · 0 completed · 0 indexed refs · 22/22 plan steps.
- Sample project "Swarm Launch Teaser" (audio-video / 45s / 120bpm) seeded with scene map + track roles + deliverables.
- All three lanes empty ("No clips yet on this lane." x3) and "No references attached yet." — backend never produced an artifact.
- Action buttons hardcoded red/pink: media-action-btn-primary, media-inline-btn-primary.

== UX / WIRING BUGS FOUND DURING WALKTHROUGH ==
1. Login overlay is dismissed but #shortcuts-help-modal re-opens on first Escape and its Close (X) button is intercepted by #troubleshoot-btn / #home-header (z-index). Reproducible.
2. Advertised Ctrl+B shortcut for Knowledge is NOT bound — pressing it does nothing. Same is likely true for Ctrl+J/Ctrl+P/Ctrl+E (not yet retested).
3. /api/diamond/residency returns HTTP 404 (no route registered). Front-end polls it and floods console with errors. Either register the route or remove the probe.
4. 4 wishlist home-cards have empty .card-title text (data-win-id: wishlist-cyber, wishlist-financial, wishlist-trading, wishlist-business). Their tile is unreadable until you hover for the title attr.
5. KC + Media Center windows render on a peach/pink background — confirms login.css fallback-color leakage; the floating-window themed CSS isn't being applied either, so the bug is broader than the login page. Theme/Sundial slice A is even higher priority than first estimated.
6. Header tab title shows "Fridays" but home-header still reads "Friday" (singular). Branding mismatch confirmed visually.

== STATE LINKAGE ==
- Inherit into existing open steps:
  - S-F7C134D9C6 (Tile-Sweep KC)   — items 1, 2, 5 above
  - S-1B90B67986 (Tile-Sweep Media)— Media Center lanes empty + red inline buttons
  - S-BAAE9C22D8 (Tile-Sweep general) — items 3, 4, 6
- New work needed: pull nomic-embed-text in Ollama OR wire alt embedder.

== RECOMMENDED NEXT MOVE ==
Slice A (Theme/Sundial token refactor) is now the unblocker for both KC and Media Center peach-background visual bugs. Slice E (/api/diamond/residency probe guard) is a 5-line fix that immediately silences console error spam.
"""

try:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, author="copilot-audit", kind="research")
except TypeError:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, kind="research")
print(f"project_id={PROJECT_ID}")
print(f"created_note_id={note.get('id') if isinstance(note, dict) else note}")
