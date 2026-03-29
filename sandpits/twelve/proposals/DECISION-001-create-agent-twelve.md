# DECISION-001: Create Agent Twelve (Time Wizard)
**Agent:** Twelve (Time Wizard)
**Date:** 2026-03-29
**Status:** EXECUTED
**Decision ID:** DECISION-001

---

## Decision

Create Agent Twelve as the Time Wizard — the swarm's temporal awareness layer.
Responsible for tracking time, managing scheduled decisions, and maintaining the
time machine (checkpoint/rollback) for all agent changes.

---

## Rationale

The swarm needed a dedicated agent for:
1. Temporal awareness — knowing what changed, when, and why
2. Decision tracking — formal DECISION-NNN workflow for architectural changes
3. Time machine — before/after snapshots for every code change
4. Checkpoint system — daily snapshots of swarm state for rollback
5. Scheduled events — future-dated work items and reminders

## Infrastructure Created

- Agent registered in `agents` table: `twelve / claude-haiku / Time Wizard`
- `memory_twelve` table: session memory pool (32 entries as of 2026-03-29)
- `decisions` table: formal decision log with proposal_file, reasoning, test_status
- `time_machine` table: code before/after snapshots linked to decisions
- `time_events` table: timestamped event stream
- `time_journal` table: agent narrative log
- `time_checkpoints` table: named state snapshots
- `daily_checkpoint` table: automated daily state captures
- Sandpit structure: proposals/, logs/, tests/, working/, archive/
- DECISION_INDEX.md: tracks all decisions

## Test Results

Bootstrap test `sandpits/twelve/tests/test_bootstrap.py`: 7/7 passed.
