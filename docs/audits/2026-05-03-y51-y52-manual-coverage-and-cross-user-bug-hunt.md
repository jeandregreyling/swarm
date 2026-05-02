# Y.51 & Y.52 — Manual coverage + cross-user / route-import bug-hunt

**Date:** 2026-05-03  
**Branch:** `proposal/GHOST_CODER-2128`  
**HEAD pushed:** `34e3d91`

## Y.51 — Manual entries for new pillars

The Y.49 orientation card promised "the ? icon on every tile opens the
manual" but Y.43 (synth-board, video-editor) and Y.47 (app-center)
shipped without populating the single-source `frontend/manual_content.py`.
Hitting "?" on those tiles 404'd.

**Added manual entries:** `app-center`, `synth-board`, `video-editor`
(plus a pass on the `orientation` entry).

**Tests:** `tests/test_y51_manual_pillar_entries.py` (6, parametrised)
* Each new pillar's `/api/manual/<key>` returns 200 with topical keywords
* `/api/manual` lists every new key
* Unknown keys still 404 cleanly (no 500)
* `app-center` body documents Y.50's archive-build block

## Y.52 — Cross-user interest leak (production bug)

`/api/interests?username=X` ignored the username filter on the
saved_interests query — `WHERE active = 1 ORDER BY score DESC LIMIT 30`.
After Y.48 seeded 37 score-8 rows for user `seven`, those rows evicted
lower-scored rows for other users from the LIMIT-30 window, surfacing as
`test_interests_wiring` failing on a clean DB.

**Fix:** `frontend/blueprints/interests_bp.py` — `/api/interests` now
honours `?username=` (defaulting to `'seven'` to match the Y.48 seed)
and threads it into the saved_interests SQL.

**Tests:** `tests/test_y52_interests_cross_user_isolation.py` (3) — pin
that ghost queries return only ghost rows, seven queries return only
seven rows, and the no-arg default doesn't leak across users.

## Y.52 — Missing /api/enrollment/invite endpoint (production gap)

`POST /api/enrollment/create` accepted invite tokens but no endpoint
issued them. `test_v8_big_items::test_enrollment_blueprint` asserted both
`/create` and `/invite` exist; only `/create` did.

**Fix:** `frontend/blueprints/enrollment.py` adds
`GET/POST /api/enrollment/invite`:
* POST issues a token (24-byte url-safe) for role
  `co_owner|assistant|member`. Validates role allow-list, role-must-be-
  string, optional email shape, and refuses to issue if no owner exists
  (409).
* GET lists the 50 most-recent invites with consumed-state.

**Tests:** `tests/test_y52_enrollment_invite.py` (7)
* POST creates token; GET lists; rejects unknown role; rejects non-
  string role; rejects bad email; token consumable by `/create` once;
  blocked when no owner exists.

## Y.52 — Order-dependent `route_imports()` (diagnostic robustness)

`ops/integration_health.py::route_imports()` failed when run after
certain test_i*.py / test_l*.py modules because earlier tests had
populated `sys.modules['services']` and `sys.modules['database']` with
namespace-only entries (no `__file__`) from a sys.path that didn't yet
include `frontend/`. Once cached that way, `importlib.import_module()`
reuses the broken shell, surfacing as ~14 false blueprint-load failures
(`cannot import name 'get_connection' from 'services' (unknown
location)`, `'services' is not a package`, etc.) despite all blueprints
working at runtime.

**Fix:** `route_imports()` now evicts namespace-shell entries
(`mod.__file__ is None`) for known shadowable names before iterating, so
imports re-resolve against the path order the function just established.
Production behaviour unchanged — only the diagnostic.

## Test results

Chunked full-suite run (a-d, e-h, i-l, m-n, o-p, r-s, t-w, v8, y4-y5,
v7c) all GREEN. `test_interests_wiring`,
`test_v8_big_items::test_enrollment_blueprint`, and
`test_integration_health_cli::test_route_imports_all_blueprints_load` now
pass cleanly — previously failed depending on test order.

## Bugs caught before the user reported them

1. Cross-user interest leak via LIMIT-30 eviction (Y.48 made it visible)
2. Missing invite-issue endpoint (advertised by /create's contract)
3. Three new pillars with broken "?" help affordance
4. Diagnostic route_imports() flaky under realistic test orders
