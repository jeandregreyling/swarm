#!/usr/bin/env python3
"""Log the June 1 system audit findings to Studio P-94531FE267.

Captures: theme/sundial bugs, app-packaging gap, KC/Music Center scope,
and links each finding to the existing open tile-sweep steps so future
work has one source of truth.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.knowledge.projects import add_blackboard_note, create_project, list_blackboard_notes


PROJECT_ID = "P-94531FE267"
CONTENT = """[AUDIT] System Audit — 2026-06-01
================================

Scope: live UI click-test + repo scan (themes, sundial, KC, Media Center,
app packaging). Server was down at start; restarted on .venv/bin/python and
all 79 blueprints loaded healthy.

Verified bugs (code-level evidence)
-----------------------------------
1. Theme picker mismatch.
   - theme.js NAMED_THEMES lists 21 themes; terminal_base.html renders only 10.
   - Missing from UI: graphite, rose, lumen, sky, solar, midnight, copper,
     neon, arctic, apple, nature, mint.
   - File: frontend/static/js/core/theme.js (NAMED_THEMES list)
           frontend/templates/terminal_base.html (#theme-picker-menu)
   - Maps to step: S-A1D1B58ED8 (Tile shell + Spotlight + Manual consistency).

2. Theme picker buttons use hardcoded inline styles.
   - Each <button onclick="setNamedTheme(...)"> sets style="...background:transparent;
     color:var(--text);..." inline; cannot be re-skinned per theme and the
     swatch dots inside also use hardcoded fills.
   - This is the likely cause of "all buttons look red" reports on warm/ember/rose.
   - Fix path: replace inline styles with a single .theme-picker-item rule in
     frontend/static/css/taskbar.css using theme tokens.

3. Sundial overlap on home.
   - #sundial-center contents (#sundial-title "Fridays" + #sundial-sub
     "Seven's Swarm") collide with rays and the inline "ep · bel · live" badge.
   - Confirmed visually on /ui home before sign-out.
   - File: frontend/static/css/diamond.css (#sundial, #sundial-center,
     .sundial-node positioning).

4. Sundial health colors are hardcoded.
   - .sundial-ray.ray-ok / ray-warn / ray-crit and .sundial-node[data-health=*]
     use literal rgba(76,175,80) / rgba(255,183,77) / rgba(239,83,80) —
     not theme-aware. Same hardcoded #ffb74d / #ff9800 throughout
     diamond.css and components.css (model-dot.dot-busy etc.).
   - Theme system therefore cannot change health palette.
   - Fix path: introduce --health-ok / --health-warn / --health-crit tokens
     per theme block in themes.css and reference from diamond.css.

5. Login screen has no theme class on <body>.
   - login.css uses var(--bg, #0d1117), var(--accent, #f7b84b) etc. with
     fallbacks. Without a body.theme-* class the page falls back to the
     mustard-peach defaults, producing the pink-tinted login form you saw.
   - Fix path: apply default theme on the login route, or seed the picker's
     saved choice from localStorage at server-side render.

6. Branding inconsistency.
   - Login title: "Friday" (singular). App tab title: "Fridays — Seven's Swarm".
   - Pick one canonical name; update both surfaces.

7. /api/diamond/residency continuously fails.
   - Repeated "[Diamond] residency: <urlopen error [Errno 111] Connection
     refused>" in server log — calling a sibling service on a port that is
     not running. Either start the residency sidecar or remove the probe
     when the upstream is absent.
   - Maps to step: S-B98A4EFF2C (Monitor/Trace/Health Digest operator view).

8. Potato Farm tile shows ERR.
   - Already tracked via S-70C1DA6B2A (Recover Potato Farm live worker)
     and the S-POTATO-* series.

App packaging
-------------
9. There is no installed Windows app.
   - windows/start-fridays.bat boots a venv + Python wrapper; windows/launcher.py
     uses a tk splash and pywebview if available.
   - PyInstaller frozen path is supported in launcher.py (sys.frozen branch)
     but no built .exe exists in windows/ and there is no installer script.
   - desktop/ contains a Tauri 2 scaffold (productName "Seven",
     identifier com.swarm.seven.desktop) targeting ./src/index.html — not
     wired to the live Flask UI.
   - Android side: android/seven-app/ has source + build_log.txt but no
     signed APK output is checked in.
   - Decision needed before any work:
     a) Ship a real PyInstaller-built Fridays.exe + an MSI/installer.
     b) Re-target the Tauri shell at http://127.0.0.1:5050/ui and ship that
        as the desktop app (smaller, native window, auto-launches Python).
     c) Stay on the .bat wrapper and stop calling it an "app".
   - Maps to step: S-E3D0688194 (Create App Center artifact trail).

Knowledge Center + Music Center
-------------------------------
10. KC and Music/Media Center are sprawling and need a structured walkthrough.
    - knowledge.js exists; no dedicated music.js — music lives inside the
      Media Center surface.
    - Existing open steps already cover the work:
        S-F7C134D9C6  Knowledge/Files/Library/Tasker on one KC bus
        S-BAAE9C22D8  Media Center handoffs via Chat/Studio/KC/Potato Farm
        S-1B90B67986  Show Me The Money loop with KC/Tasker/farm signals
    - Recommend completing audit by tile-walking each of these and attaching
      per-tile evidence notes to the matching step ID (no new top-level
      step needed yet).

Tests
-----
11. Targeted regression suite (media center, email, hive, integration):
    39 passed, 13 skipped, 0 failed. See note B-7B58D184CF on P-00221285D1.

Recommended next slices (in priority order)
-------------------------------------------
A. Theme + sundial token refactor (small CSS change, fixes findings 2/4/5).
B. Theme picker rebuild — all 21 themes in one CSS-driven list (finding 1).
C. App-packaging decision (a/b/c above) — blocks Build Readiness sign-off.
D. KC / Media Center tile-by-tile walkthrough with per-tile evidence notes.
E. /api/diamond/residency probe — guard or remove (finding 7).

No production code was changed in this audit pass; only findings logged.
"""


def main() -> int:
    target = PROJECT_ID
    try:
        note = add_blackboard_note(target, content=CONTENT, kind="research", author="codex")
    except ValueError as exc:
        if "unknown project_id" not in str(exc):
            raise
        fb = create_project(
            name="2026-06-01 Build Readiness - KC Driven Operating System",
            description="Backfilled for system audit.",
            methodology="mixed",
            owner="seven",
        )
        target = fb.get("project_id")
        note = add_blackboard_note(target, content=CONTENT, kind="research", author="codex")
    if note is None:
        raise SystemExit("failed to add audit note")
    notes = list_blackboard_notes(target, status="active", limit=3) or []
    print(f"project_id={target}")
    print(f"created_note_id={note}")
    for n in notes:
        head = (n.get("content") or "").splitlines()[0][:120]
        print(f"  {n.get('note_id')} [{n.get('kind')}] {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
