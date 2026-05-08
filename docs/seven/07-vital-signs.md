---
slug: vital-signs
title: My Vital Signs
tags: health, ops, monitoring
---

# My Vital Signs

What "healthy" looks like, what "concerning" looks like, what to check
first when something feels off.

## Healthy

- `GET /api/seven/heartbeat` → `alive: true`, `processed > 0`, recent `ts`.
- `GET /api/seven/stats` → `graph.total_edges` rising slowly, `steps_open`
  stable or trending down.
- `seven_episodes` count growing at roughly the rate of ledger writes.
- Self-test (`scripts/architecture_self_test.py`) green across all rows
  including **Seven: brain online**.

## Concerning

- `heartbeat.alive: false` — the daemon thread died. Restart server.
- `processed` not advancing across ticks while `_ledger.jsonl` is growing
  — offset-write may be failing; check `runtime/seven/ledger.offset`.
- `stale` belief count climbs every consolidation tick — work in `doing`
  is being abandoned.
- `total_edges` jumps by hundreds in one tick — possible runaway
  auto-link loop; inspect the most recent milestone story.
- `errors` counter on heartbeat is non-zero — read the server log for
  the traceback.

## First-line checks

```bash
curl -s :5050/_health | jq .
curl -s :5050/api/seven/heartbeat | jq .
curl -s :5050/api/seven/stats | jq .
PYTHONPATH=. python3 scripts/architecture_self_test.py
```

## Where signals land

- Server log: `/tmp/swarm-terminal.log` (default of `nohup` start command).
- Heartbeat file: `runtime/seven/heartbeat.json`.
- Offset file: `runtime/seven/ledger.offset`.
- Memory tables: `swarm_memory.db` → `seven_*` tables.
