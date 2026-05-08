# 2026-05-03 — Y.42 sweep + proposal-consolidator closeout

## S-FC065A010E — Inter-tile improvement sweep

The sweep step asked that the flagged surfaces beyond Media Center be pulled
into packets rather than left as flat MD-FEATURE rows. Every surface
named in its description has now landed as a tracked, shipped batch on
`proposal/GHOST_CODER-2128`:

| Flagged surface | Shipped in |
|---|---|
| chat-tile thread row | Y.18 / Y.19 |
| chat resize dragger | Y.5 |
| main-terminal thread dropdown | Y.19 |
| Studio defaults / proposals branching / GIT blocks | Y.7, Y.9 |
| Vortex section expand+resize+health | Y.9 |
| Tasker visibility/calendar placement | Y.4 |
| agents tile UX | Y.25 |
| docs/manual UX | Y.35 |
| spotlight icon compactness | Y.6 |
| feeds connectors login | Y.33 |
| KC interest suggestions | Y.21 |
| memory↔hive sync | Y.32 |
| thought-bubble persistence | Y.24 |
| local-agent banner cleanup | Y.25 |

The remaining items mentioned in S-FC065A010E either already exist in
shipped form or are tracked under V8 `[P-441A6D6476]` which is
explicitly deferred until the 7C regression gate passes. The sweep itself
is verify-closed.

## Proposal-consolidator rows (5)

`project_steps` carried five `[proposal:*]` rows whose entire body is
"Open proposal consolidated here. Agent: … | Status: …". The actual
proposal lifecycle is tracked in the `proposals` system itself — these
rows duplicate that tracking and should not be left open as parallel
todos. Closing as `done`:

| step_id | proposal | status (in proposals) |
|---|---|---|
| `S-2F47956BBA` | `proposal:DATA-GOV-20260429` | in_progress |
| `S-3AAB8396E8` | `proposal:INTERNAL-GEMMA-2127` | approved |
| `S-6C99896984` | `proposal:INTERNAL-GEMMA-2138` | approved |
| `S-DEEFB179C0` | `proposal:INTERNAL-GEMMA-2137` | approved |
| `S-FEEC88C2AB` | `proposal:INTERNAL-GEMMA-2122` | approved |

Per `STEP-STOP-MARKDOWN-TRACKER-RECREATION-20260430` (Y.14), duplicate
trackers should not be recreated. Closing the consolidator rows here so
the proposals surface stays the single source of truth.

## Kept open

* `S-53A3EC6F2D` — external music artifact link still needs the live URL
  + metadata round-trip; can't verify-close without that real check.
* `S-45064ED6C5` — `[WISHLIST] Future Major Pillars — capture-only, do not
  build yet` — kept as the system reminder.
* `MD-BUG-870F0D2F24E6` — mailto: approval-links live UAT.
* `[P-441A6D6476]` V8 cluster (17) — explicitly deferred until 7C gate.
