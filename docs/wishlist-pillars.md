# Wishlist Pillars (S-45064ED6C5)

**Status:** active v0 · each pillar has a live backend, schema, summary,
and quick-add UI. The epic stays open in perpetuity per
[continuous-improvement.md](continuous-improvement.md).

**Epic step:** S-45064ED6C5  
**Front-end surface:** 4 home tiles (Cyber Security · Financial · Trading ·
Business) — each opens a dashboard with description, **live snapshot card**,
recent items, **quick-add form**, and the underlying `project_steps`.  
**Tests:** [`tests/test_session28_batch13.py`](../tests/test_session28_batch13.py),
[`tests/test_session28_batch14.py`](../tests/test_session28_batch14.py)

## Purpose

Four future pillars the user is building out. Each pillar:

- Owns one core SQLite table (created lazily on first request).
- Exposes CRUD via `/api/<pillar>/...` plus a tight
  `/api/<pillar>/summary` Seven uses to answer questions about it.
- Renders a live dashboard tile in the home grid.
- Is wired into Seven's system prompt via
  [`_load_pillars_context()`](../agents/seven/seven_agent.py) so the LLM
  can answer "any open cyber issues?" or "how's the desk?" from real
  data, not vibes.

Sequencing: pillars stay `doing` indefinitely. They are never closed
unless the user explicitly retires one.

## Pillar backends

| Slug | Tile | Blueprint | Table | Core endpoint |
|---|---|---|---|---|
| `cyber-security` | Cyber Security | [`cybersecurity_bp.py`](../frontend/blueprints/cybersecurity_bp.py) | `cyber_audit_events` | `/api/cyber/events` |
| `financial` | Financial Analytics (IB) | [`financial_bp.py`](../frontend/blueprints/financial_bp.py) | `financial_positions` | `/api/financial/positions` |
| `trading` | Online Trading | [`trading_bp.py`](../frontend/blueprints/trading_bp.py) | `trading_signals` | `/api/trading/signals` |
| `business` | Business Centre | [`business_bp.py`](../frontend/blueprints/business_bp.py) | `business_ledger` | `/api/business/entries` |

Shared helpers (db path, id, timestamps, schema-forward `ensure_columns`)
live in [`_pillar_store.py`](../frontend/blueprints/_pillar_store.py).

## Pillar -> step_id mapping (for the wishlist tile description card)

| Slug | Tile title | Underlying `step_id`s |
|---|---|---|
| `cyber-security` | Cyber Security | `S-4697ECA1EC` |
| `financial` | Financial Analytics | `S-98CF85A8C4` |
| `trading` | Online Trading | `S-03A241D177` |
| `business` | Business Centre | `S-D618CF4B7A`, `S-25AFB74A4D`, `S-642D6439DE`, `S-B6D5701E4F`, `S-5393AEF947`, `S-2B6BC7A021` |

## API

### Per-pillar (each table is forward-compatible via `ensure_columns`)

- `GET    /api/<pillar>/<entity>?limit=&status=` — list newest first.
- `POST   /api/<pillar>/<entity>` — create; validates at boundary.
- `PATCH  /api/<pillar>/<entity>/<id>` — partial update; rejects unknown enums.
- `DELETE /api/<pillar>/<entity>/<id>` — hard delete (no soft-delete yet).
- `GET    /api/<pillar>/summary` — LLM-friendly snapshot (counts, totals, top 3-5).

### Aggregated

- `GET /api/wishlist/pillars` — metadata + step records (with `status: 'active-v0'`).
- `GET /api/wishlist/pillars/<slug>` — single pillar.
- `GET /api/wishlist/summary` — calls each `summary_for_seven()` lazily;
  a missing/broken pillar degrades to `{ok: false}` for that key, never
  500s the whole response.

Unknown slug → `404 {ok: false, error: 'unknown pillar'}`.

All endpoints degrade gracefully if `project_steps` or the pillar
table doesn't exist (fresh DB) — they return stubs / empty lists
instead of 500-ing.

## Framing notes (verbatim user cues)

- **Financial Analytics** must be **investment-banking oriented**, not
  consumer finance. Equity/FI/derivatives, M&A, deal flow, league tables.
- **Business** is an **operational centre for setting up an online business**
  — Accounting + Payroll is the spine.
- **Crypto** prefers the framing **"online trading"**.
- **Cyber Security** is a **Diamond-tier governance pillar** — sits
  alongside Vortex / Backups / Self-test. Goal: "this system is unhackable".

## Adding to a pillar

1. Add the new step row to `project_steps` (status `todo` or `doing`).
2. Append the `step_id` to the matching pillar in `PILLARS` in
   `frontend/blueprints/wishlist_bp.py`.
3. Add a parametrised case to `tests/test_session28_batch13.py` if the
   pillar's contract changes.

## Seven integration

Seven reads `_load_pillars_context()` every LLM turn and injects a tight
4-line block into the system prompt. He also has:

- A fast-path keyword match in `_compose()` for words like 'pillars',
  'wishlist', 'cyber', 'trading', 'positions', 'ledger' — returns the
  live snapshot deterministically without an LLM call.
- A `/pillars` slash command that prints the snapshot + endpoint cheat-sheet.

Do not add a fifth pillar without also extending those two paths.
