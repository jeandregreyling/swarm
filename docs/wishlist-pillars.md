# Wishlist Pillars (S-45064ED6C5)

**Status:** capture-only · do not build yet  
**Epic step:** S-45064ED6C5  
**Front-end surface:** 4 home tiles (Cyber Security · Financial · Trading · Business) — open placeholder views that read `/api/wishlist/pillars/<slug>`  
**Blueprint:** [`frontend/blueprints/wishlist_bp.py`](../frontend/blueprints/wishlist_bp.py)  
**Tests:** [`tests/test_session28_batch13.py`](../tests/test_session28_batch13.py) (14 cases)

## Purpose

The user has captured four future pillars that should not be built yet, but
must remain visible in the UI so the intent is not lost. The Wishlist tiles
are placeholder cards on the home grid — they open small views that show
the pillar's description and the underlying `project_steps` rows. They do
nothing else.

Sequencing rule: the user said *"we have enough at the moment, just log it"*.
These steps stay `todo` and are skipped by the active build queue.

## Pillars

| Slug | Tile title | Underlying `step_id`s |
|---|---|---|
| `cyber-security` | Cyber Security | `S-4697ECA1EC` |
| `financial` | Financial Analytics | `S-98CF85A8C4` |
| `trading` | Online Trading | `S-03A241D177` |
| `business` | Business Centre | `S-D618CF4B7A`, `S-25AFB74A4D`, `S-642D6439DE`, `S-B6D5701E4F`, `S-5393AEF947`, `S-2B6BC7A021` |

## API

- `GET /api/wishlist/pillars` → `{ok, epic_step_id, pillars: [...], count}`
- `GET /api/wishlist/pillars/<slug>` → `{ok, slug, tile_title, tile_subtitle, description, steps: [...]}`
- Unknown slug → `404 {ok: false, error: 'unknown pillar'}`

The endpoint degrades gracefully if `project_steps` is missing rows or the
table doesn't exist (e.g., on a fresh DB). It returns stub entries instead
of 500-ing so the front-end always renders.

## Framing notes (verbatim user cues)

- **Financial Analytics** must be **investment-banking oriented**, not
  consumer finance. Equity/FI/derivatives, M&A, deal flow, league tables.
- **Business** is an **operational centre for setting up an online business**
  — Accounting + Payroll is the spine.
- **Crypto** prefers the framing **"online trading"**.
- **Cyber Security** is a **Diamond-tier governance pillar** — sits
  alongside Vortex / Backups / Self-test. Goal: "this system is unhackable".

## Adding to a pillar

1. Add the new step row to `project_steps` (status `todo`).
2. Append the `step_id` to the matching pillar in `PILLARS` in
   `frontend/blueprints/wishlist_bp.py`.
3. Add a parametrised case to `tests/test_session28_batch13.py` if the
   pillar's contract changes.

Do **not** wire any feature behaviour to a wishlist tile until the user
explicitly takes that pillar out of capture-only.
