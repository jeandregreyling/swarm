# Continuous Improvement — pillar build loop

**Created:** 2026-05-02 (Session 28, batch 14)  
**Owner:** seven  
**Project:** P-00221285D1  
**Epic:** S-45064ED6C5 (Wishlist)

## Operating principle

The wishlist pillars are **never done**. They flip from `todo` →
`doing` once they have a live backend (where we are now) and stay in
`doing` indefinitely while we layer features on top. They only flip
to `done` if and when the user explicitly retires the pillar.

This document captures the loop we run **every** time we touch a pillar,
so improvements compound instead of leaking entropy.

## The loop (per pillar, per change)

1. **Schema first** — if the change adds a new field, add it to the
   `_init` table create AND to `ensure_columns()` so old DBs upgrade
   on next write.
2. **API second** — extend the blueprint with a new route OR widen an
   existing route's accepted body. Validate at the boundary, never
   inside the route body.
3. **Summary third** — if the new data should influence Seven's
   answers, extend `summary_for_seven()`. Keep it tight — Seven gets
   ~6 lines of pillar context, not a wall.
4. **UI fourth** — extend the headline pairs / form bodyFn in
   `pillar_live.js`. Never let the UI be the only place a value is
   computed.
5. **Tests last** — add a case to `tests/test_session28_batch14.py`
   (or its successor) covering: list, create-validation, summary-shape,
   missing-table-survival.

## Quality gates (must remain green before any commit touches a pillar)

| Gate | Where | How to run |
|---|---|---|
| Pillar API contract | tests/test_session28_batch14.py | `pytest tests/test_session28_batch14.py -q` |
| Wishlist aggregator | tests/test_session28_batch13.py | `pytest tests/test_session28_batch13.py -q` |
| Seven context wiring | tests/test_session28_batch14.py::test_seven_pillars_block | (subset of above) |
| Tile wiring | tests/test_session28_batch13.py | (already covered) |
| Live smoke | curl `/api/wishlist/summary` | should return `ok=True` and 4 pillar keys |

If a gate fails: **fix it before touching anything else.** No
commits-with-failing-tests, no skipped tests, no `xfail` to dodge red.

## Continuous improvement triggers

These are the events that should cause us to improve a pillar (in
order of priority):

1. **User logs an entry that doesn't fit** → add a field or a kind.
2. **Seven answers vaguely about a pillar** → enrich
   `summary_for_seven()`.
3. **A pillar gathers >50 rows** → add a filter / archive endpoint.
4. **A row dies in `draft` for >7 days** → add a cleanup tasker.
5. **A new data source becomes available** (e.g. live market data,
   exchange API, accounting export) → wire it through a separate
   blueprint that *writes into* the pillar table; don't merge sources
   into the pillar blueprint itself.

## What we will NOT do

- We will not turn a pillar into a generic CRUD platform. Each table
  has a deliberate schema; resist the urge to add `metadata JSON`
  columns. Add a real column with a real type.
- We will not let the front-end author authoritative state. Always
  POST → server → re-read.
- We will not let the LLM hallucinate pillar facts.
  `_load_pillars_context()` is the only path that surfaces pillar
  state into Seven's prompt; it always reads live SQLite.
- We will not promote pillars to `done`. They are perpetually
  `doing` while the system is alive.

## Stamp of excellence

- Schema is forward-compatible (`ensure_columns` on every read).
- Endpoints are idempotent on read, validating on write, 404-safe.
- Each pillar's summary is small enough to fit in Seven's prompt.
- Each blueprint is < 250 lines and obvious from a single read.
- Each test file passes in < 5 seconds in isolation.
- The user can stand up a usable pillar by tapping the tile and
  typing one line into the quick-add box.

This is the bar.
