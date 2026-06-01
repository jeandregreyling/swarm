# Quintum Chunking — Small-Model Studio Task Delegation

**Project ID:** P-5C3A1F2B4E  
**Status:** active  
**Owner:** Seven  
**Created:** 2026-06-01  
**Theme:** Local-first agent task execution with online validation

---

## Overview

Small local models (Gemma3, Qwen2.5) should be able to own and complete Studio
project steps without a large cloud model being required for every task. The
blocker has always been context window pressure — a local 7B model struggles
when the full project description, all Blackboard notes, and a complex task
description are dumped in at once.

**Quintum chunking** solves this by:

1. Breaking the full project/step context into focused chunks before sending to
   the local model.
2. Feeding each chunk through the local model with a narrowly scoped question.
3. Accumulating partial answers on the Blackboard as structured notes.
4. Letting the local model synthesise across its own Blackboard notes rather
   than the full original blob.
5. Routing only the final synthesis to an online validator (Nine / Eleven /
   Twelve) which checks correctness and marks the step done.

This keeps the expensive model at the quality-gate edge only. All actual work
runs locally.

---

## Designated Agents

| Role | Agent | Model | Responsibility |
|---|---|---|---|
| Studio watcher | **Gemma** | gemma3:latest | Polls `todo` steps, claims them, drives chunked work |
| Analyst | **Qwen** | qwen2.5:latest | Second-pass reasoning on complex chunks if Gemma is uncertain |
| Validator | **Nine** (or Eleven) | GPT-4o / Claude | Reads Blackboard synthesis, confirms or bounces the step |

Gemma is the right Studio watcher because it already reads open ticket counts
from DB (`_build_context`) and its existing role is "Orchestrator". It needs
to be extended to also read `project_steps` with `status='todo'` and no claimed
owner.

---

## Quintum Chunking — How It Works

```
Step description (large)
        │
        ▼
  chunk_split()            ← splits on logical boundaries (headings,
        │                     sentences, numbered items); max ~800 tokens/chunk
        ├── chunk 1 ──► gemma: "What is the action item here?"
        ├── chunk 2 ──► gemma: "What is the action item here?"
        └── chunk N ──► gemma: "What is the action item here?"
                                │
                      partial answers written to Blackboard
                                │
                      gemma synthesis pass:
                      "Given these notes, what is my final answer?"
                                │
                      Blackboard: synthesis note (tag: 'quintum-synthesis')
                                │
                      validator reads synthesis → approves or bounces
```

The "quintum" name comes from the five-part cycle: **split → probe → note →
synthesise → validate**. Each pass is smaller than what a 7B model can
comfortably hold, so the model grips the input rather than losing it in the
middle of a long context.

---

## Steps

- [x] **QT-01 — Studio open-task query** — `list_open_steps(owner=None, limit=10)` exists in `core/knowledge/projects.py`. June 1 hardening: treats orchestration-default `owner='seven'` as claimable so Studio steps are not hidden behind the default owner policy.

- [x] **QT-02 — Step claim** — `claim_step(step_id, agent_name)` exists in `core/knowledge/projects.py`. June 1 hardening: compare-and-swap now also accepts the orchestration default owner so claims work against real Studio rows.

- [x] **QT-03 — Chunk splitter** — `core/chunk/quintum.py` exists with `chunk_split(text, max_tokens=800)` plus context-prefix support for repeated shared project context.

- [x] **QT-04 — Gemma Studio watcher** — `agents/gemma/gemma_agent.py` now exposes a live top-level `watch_studio(max_steps=3)`. June 1 fix pulled it out of dead nested code, added project-context packing, chunk probing, Blackboard writes, synthesis, and status transitions.

- [ ] **QT-05 — Validator hook** — Add a route or queue entry that sends the synthesis Blackboard note to Nine (or Eleven) with a structured prompt: "Does this answer satisfy the step requirement? Reply YES/NO and brief reason." If YES, mark step `done`. If NO, write a bounce note and reset step to `todo` (incrementing a retry counter).

- [x] **QT-06 — Scheduler wiring** — `fridays/task_runner.py` already had the registered task. June 1 fix repaired `fridays/scheduler.py` so `setup_studio_watcher_task()` actually runs at startup instead of sitting inside the wrong `except` block. Watcher now self-skips when Ollama is offline.

- [x] **QT-07 — Blackboard tag rendering** — Studio project UI now renders `quintum-chunk` and `quintum-synthesis` Blackboard kinds with dedicated badges and constrained note bodies so chunk spam does not drown the rest of the project feed.

- [x] **QT-08 — Model-size routing** — Gemma watcher now estimates the combined step + project-context payload before claim. Oversized work is left with `owner='skip-too-large'` instead of being blindly swallowed by a 7B model.

---

## Architecture Constraints

- **No model duplication**: quintum chunking is chunking the *prompt*, not re-downloading models.
- **Blackboard is the shared memory**: all intermediate answers go to Blackboard, not in-memory. This makes the work resumable across restarts.
- **Validator is optional at first**: the watcher should work without a validator — it just leaves the synthesis note for a human to review and mark done manually.
- **No forced online call**: if no paid agent is available (keys not set), the step stays at `todo` after synthesis. The validator is a bonus, not a blocker.
- **Retry cap**: max 3 retries per step before marking `blocked` and writing a note explaining why.

---

## Blackboard

**2026-06-01** — Project created. Models are now up and running on shared NTFS
partition (`F:\.ollama\models`). WSL-to-Windows Ollama routing fixed via
`_resolve_ollama_host()` in `localai.py` (reads Windows gateway from
`/etc/resolv.conf`). Local agents are now reachable — unblocked for
implementation.

Gemma3 and Qwen2.5 both confirmed in the live Ollama model list. Validator
candidates: Nine (GPT-4o), Eleven (Claude/Anthropic), or Twelve.

**2026-06-01 (later)** — First Quintum sweep landed for real. The earlier
state was misleading: QT-01/02/03 and fragments of QT-04/06 already existed,
but the watcher lived under a dead indentation block, Blackboard kinds did not
support Quintum notes, and the scheduler registration was stranded inside the
wrong exception path. Hardening landed across `projects.py`,
`agents/gemma/gemma_agent.py`, `fridays/scheduler.py`, and the Studio UI.
QT-05 remains the main open item because validation still uses direct model
calls rather than a durable queue/route with bounce accounting.
