# Y.53 & Y.54 — Type-check propagation across media surfaces

**Date:** 2026-05-03  
**Branch:** `proposal/GHOST_CODER-2128`  
**HEAD pushed:** see push log

## Context

Y.50 fixed three production-readiness bugs in `app_center` of the form
`(body.get('x') or '').strip()` crashing on non-string input. The pattern
was copy-pasted into every other Y.43+ media blueprint; Y.53/Y.54
finishes the sweep so SQLite's permissive typing can't sneak past us.

## Y.53 — synth_board + video_editor

`frontend/blueprints/synth_board.py::create_board`
* type-check name/owner/key/notes (must be string-or-None)
* type-check tempo (must be number, range 0–600)

`frontend/blueprints/video_editor.py::create_timeline`
* type-check name/owner/project_id/resolution/notes (string-or-None)
* type-check duration_seconds/fps (number, ≥ 0)

`frontend/blueprints/video_editor.py::render_timeline`
* type-check agent (string-or-None)

**Tests:** `tests/test_y53_synth_video_type_checks.py` (18, parametrised)
covering rejected non-string fields, rejected bad numerics, and happy-
path regression on both surfaces.

## Y.54 — media_jobs (queue handoff)

`frontend/blueprints/media_jobs.py::submit_job`
* type-check kind/agent (string)
* type-check priority (number, range 0–10)

`frontend/blueprints/media_jobs.py::update_job`
* type-check status/asset_id/error (all string-or-None)
* cap asset_id at 256 chars (parity with Y.50 app_center fix)

This blueprint is hit by app_center, video_editor, and the synth board's
implicit render path, so a single bad client field could 500 the whole
media pipeline. Now it 400s cleanly and tells the caller exactly which
field was bad.

**Tests:** `tests/test_y54_media_jobs_type_checks.py` (8, parametrised)
covering 3 submit field types, priority range, 3 patch field types, and
the asset_id length cap.

## Bugs caught before reporting (Y.50 → Y.54 sweep)

1. app_center: archive blocks build (Y.50)
2. app_center: invalid `?target=` returned empty list (Y.50)
3. app_center: PATCH non-string fields → 500 (Y.50)
4. synth_board: POST non-string name/owner/key/notes → 500 (Y.53)
5. synth_board: POST non-numeric / out-of-range tempo → 500 (Y.53)
6. video_editor: POST non-string fields → 500 (Y.53)
7. video_editor: POST non-numeric duration/fps → 500 (Y.53)
8. video_editor: render non-string agent → 500 (Y.53)
9. media_jobs: POST non-string kind/agent or non-number priority → 500 (Y.54)
10. media_jobs: PATCH non-string status/asset_id/error → 500 (Y.54)
11. media_jobs: PATCH unbounded asset_id length (Y.54)

Total: 11 production-readiness bugs found and fixed proactively across
the Y.43+ media-pillar surfaces.
