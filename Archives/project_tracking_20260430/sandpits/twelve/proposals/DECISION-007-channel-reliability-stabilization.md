# Decision 007: Channel Reliability Stabilization (Telegram, Discord, Email)

Status: EXECUTED (Slice 1)
Decision ID: 007
Date: 2026-03-30
Agent: Copilot (Ghost Layer)

## Problem
Operator reports indicate practical reliability drift across channel front doors:
- Telegram responses inconsistent
- tickets opened without complete processing
- email requests with no visible response
- Discord behavior inconsistent

## Root Cause (Slice 1 Findings)
1. Channel pipelines mark queue entries as `processing` before multi-stage orchestration.
2. On pipeline exceptions, handlers returned user-facing error messages but had no explicit queue reset path in-channel.
3. This made queue/ticket lifecycle appear half-complete to operators until later cleanup loops.

## Implemented in Slice 1
1. Added queue recovery helper:
- `core/pipeline/queue_manager.py`
- `mark_failed(queue_id, reason)` resets queue row to `queued`.

2. Added explicit failure recovery in channel pipelines:
- `fridays/telegram_bot.py`
- `fridays/discord_bot.py`
- Both now:
  - catch pipeline exceptions inside `_run_pipeline`
  - call `mark_failed(queue_id, reason)`
  - log `pipeline_failed` activity with ticket reference
  - re-raise so caller still replies with a failure message

3. Governance + evidence updates:
- `docs/BUGS.md` updated with BUG-028 and BUG-029
- `docs/UAT_TEST_SCRIPTS.md` expanded with Section 7 channel reliability tests
- `docs/TASK_TRACKER_LIVE.md` updated with Session 6 stabilization backlog items

## Why This Decision
This keeps ALM/Vortex traceability intact while reducing practical channel dead-ends. Queue recovery becomes deterministic at the failure point instead of waiting for external restart cleanup.

## Next Slice
1. Execute full Section 7 UAT cycle for Telegram/Discord/Email.
2. Capture pass/fail in TEST-007 and promote validated fixes to full complete status.
3. Verify Vortex slider preview on primary 5050 service after restart.
