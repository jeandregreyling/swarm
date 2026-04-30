# Proposal: Time Wizard Fix + Fridays Internal Proposal Queue
**Agent:** Nine (System Architect)
**Date:** 2026-03-29
**Status:** EXECUTED
**Proposal ID:** NINE-019

---

## What I Proposed

Two related architectural changes:

1. **Fix Time Wizard (Twelve)** — complete the missing sandpit structure and DB schema so bootstrap tests pass 7/7.
2. **Fridays Internal Proposal Queue** — every agent action (skill calls, file writes, self-executed changes) must create a `work_proposals` entry AND be visible in a shared queue. All agents can see and contribute to the queue.

---

## Part 1: Time Wizard Fixes

### Problem
Bootstrap test `sandpits/twelve/tests/test_bootstrap.py` fails 2/7 checks:
- Missing `sandpits/twelve/working/` directory
- Missing `sandpits/twelve/archive/` directory
- Missing `sandpits/twelve/proposals/DECISION-001-create-agent-twelve.md`

Additionally:
- `decisions`, `time_machine`, `time_events`, `time_journal`, `time_checkpoints`, `daily_checkpoint` tables exist in the live DB but are absent from `database.py` SCHEMA and `_migrate_schema()` — new installs would be missing them
- `memory_grok` and `memory_twelve` are in `AGENT_POOL_MAP` but absent from SCHEMA — same problem
- `fridays/scheduler.py` `main_loop()` calls `run_daily_digest()` and `check_snoozed()` every 60s but never calls `check_due()` — scheduled tasks never fire

### Fix
1. Create `sandpits/twelve/working/` and `sandpits/twelve/archive/` directories
2. Create `sandpits/twelve/proposals/DECISION-001-create-agent-twelve.md` — the bootstrap marker file
3. Add all missing tables to `database.py` SCHEMA and `_migrate_schema()`
4. Wire `check_due()` into `scheduler.py` `main_loop()`

---

## Part 2: Fridays Internal Proposal Queue (Architectural Change)

### Problem
Currently, agent actions flow into three separate log systems (ghost_circle, sandpit_log, activity_log) but are invisible to the ticket/queue system. If Nine fixes a bug or Fridays writes a file, there is no ticket, no proposal entry, and no way for other agents to see it in the shared queue.

The user's requirement: **every agent action — including self-executed ones — should create a ticket and be logged as a proposal. All agents should be able to see and edit the queue.**

### Design

#### New `work_proposals` table
Tracks all internal agent proposals/actions as first-class entries:
```
work_proposals(id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, created_at, updated_at)
```
Status values: `pending` | `approved` | `rejected` | `executed`

#### Queue table additions
Add two columns to `queue`:
- `source_type TEXT DEFAULT 'email'` — distinguishes `email` / `telegram` / `internal` entries
- `agent TEXT DEFAULT ''` — originating agent for internal entries

#### New `queue_manager.intake_internal()`
Agents call `intake_internal(agent, title, description, priority=5)` to create a queue entry + work_proposal record atomically. Returns `(queue_id, proposal_id)`.

#### Fridays skills.py — proposal logging
After every `file_write` or `shell` skill call that succeeds, create a `work_proposals` entry via `intake_internal()`. This ensures every Fridays-executed change is visible in the queue.

#### New terminal.py API endpoints
- `GET /api/queue` — returns all queue entries (email + telegram + internal), filterable by `source_type` and `status`
- `POST /api/queue` — any agent can add an internal queue entry
- `GET /api/queue/<id>` — single queue entry detail
- `PATCH /api/queue/<id>` — update status or notes on any entry

---

## Files Changed

| File | Change |
|------|--------|
| `sandpits/twelve/working/` | Created (directory) |
| `sandpits/twelve/archive/` | Created (directory) |
| `sandpits/twelve/proposals/DECISION-001-create-agent-twelve.md` | Created (bootstrap marker) |
| `utils/database.py` | Added 8 missing tables to SCHEMA; queue source_type + agent columns; _migrate_schema entries |
| `core/pipeline/queue_manager.py` | Added `intake_internal()` |
| `fridays/skills.py` | Added `_log_as_internal_proposal()`, called after file_write/shell success |
| `frontend/terminal.py` | Added `/api/queue` GET/POST, `/api/queue/<id>` GET/PATCH |
| `fridays/scheduler.py` | Wired `check_due()` into `main_loop()` |
| `sandpits/nine/NINE_DECISION_INDEX.md` | Updated with NINE-019 |
| `docs/CHANGELOG.md` | Updated |

---

## Impact

- **Time Wizard bootstrap tests:** 7/7 pass (was 5/7)
- **Scheduler:** Scheduled tasks now fire on time (check_due was unreachable before)
- **Fridays writes:** Every file_write/shell action now creates a work_proposal visible to all agents
- **Queue:** Unified view of email, Telegram, and internal agent work — all readable and writable via API
- **Architectural coherence:** Agent self-actions are now first-class citizens in the same queue as external requests
