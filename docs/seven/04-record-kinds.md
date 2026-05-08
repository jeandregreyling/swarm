---
slug: record-kinds
title: Record Kinds
tags: records, schema, ids
---

# Record Kinds

Ten kinds live in `runtime/records/<kind>/<yyyy>/<mm>/<id>.{json,md}`.
Every kind has an append-only ledger entry on save and a typed-edge graph
in `_links.db`.

| Prefix | Kind        | Meaning                                              |
|--------|-------------|------------------------------------------------------|
| `B-`   | note        | Blackboard notes; milestones live here               |
| `S-`   | step        | Project steps (the work-in-flight ledger)            |
| `P-`   | project     | Project containers (P-00221285D1 = Studio backbone)  |
| `PR-`  | proposal    | Studio proposals (governance pre-step)               |
| `T-`   | ticket      | User-facing issues / questions                       |
| `TC-`  | case        | Test-lab cases                                       |
| `TR-`  | test_run    | Test-lab runs                                        |
| `D-`   | doc         | Project docs                                         |
| `TH-`  | thread      | Long-form discussion threads                         |
| `(special)` | (other) | Reserved for future kinds                            |

## Inference

`core.seven.perception._kind_of(record_id)` infers kind from prefix.
`core.seven.reasoning._pick_kind(record_id)` does the same.

## Where they live in code

- Storage: `core.records.store`
- Graph: `core.records.links` (`record_links` table in `_links.db`)
- Ledger: `runtime/records/_ledger.jsonl`
- Sidecars: every `.json` has a `.md` for human-readable diffs.
