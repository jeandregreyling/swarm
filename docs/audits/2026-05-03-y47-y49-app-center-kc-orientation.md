# Y.47 → Y.49 Audit — App Center, KC seed/overview, and first-run orientation

**Branch**: proposal/GHOST_CODER-2128
**Range**: `c53c1ad` → current HEAD
**Scope**: Three batches in autonomous burn-down — App Center pillar, KC
seed + overview surface, and first-run orientation card.

## Y.47 — App Center pillar (blueprint #74)

User request: *"Oh and we also need an App center where we can build
mobile/tab/computer apps and games"*.

* `frontend/blueprints/app_center.py` — fresh blueprint with three tables:
  * `app_projects` (project_id `APP-*`, name, kind, framework, owner,
    description, repo_ref, status, studio_project_id, tags_json, timestamps).
  * `app_project_targets` — UNIQUE(project_id, target), per-target build status,
    last_build_id reference.
  * `app_builds` (build_id `BUILD-*`, status, media_job_id, asset_id, error,
    agent, timestamps).
* Validation contracts (returns 400 on violation):
  * `_VALID_KINDS`: mobile, tablet, desktop, web, game.
  * `_VALID_FRAMEWORKS` (22): flutter, react-native, expo, ionic, native-android,
    native-ios, electron, tauri, qt, gtk, next, sveltekit, astro, pwa, godot,
    unity, unreal, phaser, love2d, pygame, custom, …
  * `_VALID_TARGETS` (9): ios, android, windows, macos, linux, web, wasm,
    itch, steam.
  * `_VALID_PROJECT_STATUS`: draft, active, paused, archived.
  * `_VALID_BUILD_STATUS`: queued, building, succeeded, failed, cancelled.
* Endpoints under `/api/app-center/*` (8): create/list/get/patch project,
  add target (409 on duplicate), kick build, list builds, patch build,
  registry endpoint (lists every kind/framework/target/status string the
  client can consult).
* Build queue handoff via `core.pipeline.queue_manager.intake_internal(agent,
  title, desc, priority=5)`. Queue intake failures return **HTTP 502** and
  persist a `failed` build row — same contract introduced in Y.44 for
  `video_editor.queue_render`.
* Default agent for builds: `ghost_coder`.
* Tests: `tests/test_app_center.py` (9). Lifecycle, validation per field,
  duplicate-target 409, queue-failure 5xx + persisted `failed` row, kind /
  framework filters on listing.

## Y.48 — KC seed + overview (blueprint #75)

User request: *"You also need to seed the entire KC with all the new stuff
and while you're at it, make it amazing and useful"*.

* `frontend/blueprints/media_curriculum.py` — `_VALID_KINDS` extended with
  `app` and `game` so the KC topic↔tool table can carry App Center entries.
* `scripts/seed_kc_y48.py` — idempotent seed (re-running merges via
  `INSERT … ON IntegrityError → UPDATE notes`).
  * `kc_media_curriculum` ~50 rows across music, image, video, style, genre,
    production, app, game.
  * `user_interests` ~37 rows across `media_synth`, `media_video`, `apps`,
    `apps_framework`, `apps_target`, `games`, `games_engine`, `games_platform`
    — attributed `source='seed', source_agent='librarian', score=8.0`.
* `frontend/blueprints/kc_overview.py` — `GET /api/kc/overview` returns:
  * curriculum totals + by-kind breakdown + top topics by tool count.
  * `kc_media_trace` row count (informational).
  * user_interests totals + seeded count + by-category.
  * per-pillar stats for `app_center`, `synth_board`, `video_editor`,
    `knowledge_sources` — defensive against missing tables, so the surface
    works on a half-set-up DB.
* Tests: `tests/test_y48_kc_seed.py` (4). Idempotency, new-pillar coverage
  (kinds + categories), overview-endpoint reports new pillars after a fresh
  App Center create, media_curriculum accepts `kind=app|game`.
* Real DB seed run on `swarm_memory.db`: 48 inserted, 1 merged, 37 interests.

## Y.49 — First-run orientation card

User feedback (`STEP-DOCS-UX-BC3D33C260`): *"The Help tile is hard to find on
first launch"* + *"confused about the search bar"*.

* `frontend/manual_content.py` — new `orientation` entry in the single-source
  manual. Explains where Help (`?`) is, what the Spotlight search bar does,
  and that the Manual tile opens the full doc.
* `frontend/blueprints/orientation.py` — new blueprint #76 with three
  endpoints:
  * `GET /api/orientation/seen` → `{ seen, version, seen_at?, previous_version? }`.
  * `POST /api/orientation/dismiss` → marks the current `_VERSION` as seen for
    the active user.
  * `POST /api/orientation/reset` → re-shows the card.
  * Per-user (`?user=`), default `seven`. Bumping `_VERSION` invalidates
    previous dismissals — escape hatch for orientation-content updates.
* Frontend wiring:
  * `frontend/templates/terminal_base.html` — orientation card markup at the
    top of the home tiles section + `<script src=…/orientation_card.js>`.
  * `frontend/static/js/views/orientation_card.js` — fetches `/seen`, shows
    or hides accordingly, dismiss button posts to `/dismiss`, "Open the
    orientation manual entry" link calls `openWindowHelp('orientation')`.
* Tests: `tests/test_y49_orientation.py` (9).
  * Manual entry served at `/api/manual/orientation` and listed in
    `/api/manual` keys.
  * `seen=false` initially, dismiss → seen=true, reset → seen=false again.
  * Per-user isolation (alice dismissed ≠ bob seen).
  * Version bump invalidates dismissal.
  * Template + JS contract checks (markup + endpoint URLs present).

## Test isolation regression fixed (carried inside Y.47 commit)

While shipping Y.47 a real-DB leak surfaced: existing media-workspace tests
patched `frontend.blueprints.<name>` for `_DB_PATH`, but the running app
loads the same blueprints via `importlib.import_module('blueprints.<name>')`
because `frontend/terminal.py` injects `frontend/` onto `sys.path`. Python
treats those as two distinct module objects, so the test patches only
mutated the alias and routes kept writing to the real `swarm_memory.db`.

Fix applied across `tests/test_app_center.py`,
`tests/test_media_workspaces.py`, `tests/test_y44_proactive_bug_fixes.py`,
`tests/test_y45_patch_validation.py`, `tests/test_y49_orientation.py`:
patch BOTH module aliases (`blueprints.<name>` and
`frontend.blueprints.<name>`), and for routes that captured
`from services import get_connection` at import time also rebind the
attribute on the loaded module.

## Counts

* Suite slice: 90 → 112 GREEN (+9 Y.47, +4 Y.48, +9 Y.49).
* Blueprints: 73 → 76 (`app_center`, `kc_overview`, `orientation`).
* New tables: `app_projects`, `app_project_targets`, `app_builds`,
  `orientation_seen`. Plus seeded `kc_media_curriculum` and `user_interests`.
* Project burn-down: 732 → 733 done, 23 → 21 todo (the +1 closes
  `STEP-DOCS-UX-BC3D33C260`; the V8 cluster + 4 keep-open rows remain
  intentionally open).
