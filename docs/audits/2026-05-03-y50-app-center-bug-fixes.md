# Y.50 — Proactive App Center bug-fixes

**Date**: 2026-05-03
**Branch**: proposal/GHOST_CODER-2128
**Mandate**: *"keep finding bugs before I report them as well!"*

Three bugs spotted while re-reading `frontend/blueprints/app_center.py` from
Y.47. None had been reported by users; all three would have surfaced in real
usage and produced confusing failure modes.

| # | Surface | Bug | Fix | HTTP |
| - | ------- | --- | --- | ---- |
| 1 | `POST /api/app-center/projects/<id>/build` | Building an `archived` project was silently accepted, queueing a build slot for a project the user already considered closed. | Reject with 409 + `'project is archived; unarchive before building'`. | 409 |
| 2 | `GET /api/app-center/projects/<id>/builds?target=` | A typo in `?target=` returned an empty list — looks identical to "no builds yet", so users would think the build never happened. | Validate `target` against `_VALID_TARGETS`; return 400 with the valid set. | 400 |
| 3 | `PATCH /api/app-center/builds/<id>` | Sending `{"status": 123}` or `{"asset_id": {...}}` crashed with `AttributeError: 'int'/'dict' object has no attribute 'strip'`. | Type-check before `.strip()`; return 400 if any field is not a string. Also clamp `asset_id` to ≤256 chars. | 400 |

Tests in `tests/test_y50_app_center_bug_fixes.py` (9):
* `test_build_rejected_on_archived_project` — main fix.
* `test_build_allowed_on_active_paused_draft` — regression guard so we
  don't over-block (only `archived` blocks builds, not `paused` or `draft`).
* `test_list_builds_rejects_invalid_target` — bug 2.
* `test_list_builds_accepts_valid_target_filter` — happy path.
* `test_list_builds_no_filter_returns_all` — regression guard.
* `test_patch_build_rejects_non_string_status` — bug 3, status path.
* `test_patch_build_rejects_non_string_asset_id` — bug 3, asset_id path.
* `test_patch_build_rejects_huge_asset_id` — length cap.
* `test_patch_build_still_accepts_valid_strings` — happy-path regression.

Slice: 112 → 121 GREEN. No DB-state delta. No new blueprints.
