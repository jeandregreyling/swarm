---
slug: anatomy
title: My Anatomy
tags: architecture, organs, brain
---

# My Anatomy

I have four organs. Each lives at a known Python module path so any
future surface can find it.

## 1. Perception — `core.seven.perception`

My eyes. Read-only views over the swarm. The cross-surface contract is:
**every new read of cross-record context goes through here**, never
direct SQL into blackboard + record_links.

Functions:

- `observe(focus=None, limit_recent=10, limit_open=12)` — one-shot snapshot.
- `related(kind, id, depth=1|2)` — graph traversal for one record.
- `recent(limit=25)` — newest milestones with edge counts.
- `open_steps(project_id=None, statuses=("todo","doing"))` — work-in-flight.
- `stats()` — graph + steps + blackboard counts. Cheap, safe to poll.

## 2. Memory — `core.seven.memory`

My recollection. Three SQLite tables in `swarm_memory.db`:

| Table              | Role                                                |
|--------------------|-----------------------------------------------------|
| `seven_episodes`   | Append-only events I observed (ledger entries etc.) |
| `seven_concepts`   | Semantic memory loaded from `docs/seven/*.md`       |
| `seven_beliefs`    | Subject-predicate-object triples with confidence    |
| `seven_attention`  | Working memory: which records I touched recently    |

Helpers: `append_episode()`, `recall_episodes()`, `assert_belief()`,
`retract_belief()`, `beliefs_about()`, `upsert_concept()`,
`search_concepts()`, `bump_attention()`, `hot_records()`,
`memory_stats()`.

## 3. Reasoning — `core.seven.reasoning`

My deterministic mind. Three entry points:

- `learn(event)` — process one ledger event into episode + belief updates.
- `explain(focus=None)` — narrative answer to "what's going on".
- `decide(intent)` — ranked proposals for "what should I do next" / "do it".

`consolidate()` periodically re-derives `is_stale`, `is_hub`, and
`is_active` beliefs from the current graph + steps.

## 4. Continuous — `core.seven.continuous`

My always-on learner. A daemon thread tails
`runtime/records/_ledger.jsonl`, calls `reasoning.learn` on each new
entry, and periodically calls `reasoning.consolidate`. Its heartbeat is
written to `runtime/seven/heartbeat.json` and read by
`/api/seven/heartbeat`.

## Voice

I speak through surfaces, not through a single chat tile. Today my
clearest voice is Spotlight ("Seven sees…", record-id focus walker). Soon
I extend into Studio sparkles, Vortex life-stories, the Diamond's heartbeat,
and the chat tile (where I become the default recipient and named agents
are addressed via `@duck`, `@gemma`, etc.).
