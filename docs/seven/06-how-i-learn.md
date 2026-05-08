---
slug: how-i-learn
title: How I Learn
tags: learning, episodes, beliefs
---

# How I Learn

Three loops compose my learning.

## 1. Episodic loop (continuous)

`core.seven.continuous` tails `runtime/records/_ledger.jsonl`. Every line
becomes one row in `seven_episodes` via `reasoning.learn(event)`. Each
episode carries a salience score derived from the kind + action:

| Kind     | Salience |
|----------|---------:|
| note     |     0.85 |
| proposal |     0.70 |
| ticket   |     0.65 |
| step     |     0.55 |
| case     |     0.55 |
| test_run |     0.50 |
| doc      |     0.45 |
| thread   |     0.40 |
| project  |     0.30 |

Working memory (`seven_attention`) is bumped at the same time so
`hot_records()` reflects what is moving right now.

## 2. Belief loop (per-event + periodic)

`learn(event)` runs a small set of explicit rules:

- **R1** — every save asserts `(kind:id, exists, true)` confidence 0.95.
- **R2** — last writer claims `(kind:id, last_actor, <actor>)` confidence 0.6.
- **R3** — saves of `note` kind assert `(note:id, is_milestone, true)` 0.9.
- **R4** — deletions retract `exists` and assert `deleted` confidence 1.0.

Periodically, `reasoning.consolidate()` re-derives:

- `(step:id, is_stale, true)` for steps in `doing` >7 days.
- `(note:id, is_hub, true)` for notes with edge_count ≥ 3.
- `(packet:PACKET-N, is_active, true)` for packets with open child steps.

Beliefs are evidence-counted. Re-asserting pulls confidence toward the
new value weighted by evidence count, so noisy single events do not
overwrite a strong belief.

## 3. Curriculum loop (manual)

`docs/seven/*.md` is my textbook. New entries become semantic memory on
restart (or on `POST /api/seven/concepts/reload`). To teach me a new
concept: drop a markdown file in that folder.

## What happens at each tick

```
[ledger line appears]
        │
        ▼
  reasoning.learn(event)
        │
        ├── seven_episodes  +1 row
        ├── seven_attention bump
        └── seven_beliefs   R1..R4
        │
        ▼ (every CONSOLIDATE_EVERY_S)
  reasoning.consolidate()
        │
        └── derived beliefs refreshed
```

Suggestions read this state, not the raw graph alone, so my "what should
I do next" gets sharper as I learn.
