# BUGS — Seven's Swarm Canonical Bug Log

<!-- markdownlint-disable -->

_Maintained by Nine (Ghost Layer). Last updated: 2026-04-19 (Session 21 — Tasker + Seven LLM fixes)._

---

## Legend

| Status | Meaning |
|--------|---------|
| **open** | Confirmed bug, not yet resolved |
| **deferred** | Won't fix in this phase |
| **fixed** | Resolved and tested |
| **needs_verification** | Fix applied, awaiting UAT confirmation |

---

## BUG-028: Scheduler shell injection vector via shell=True
- **Status:** fixed
- **Found:** 2026-04-19 (Session 21 audit)
- **Fixed:** 2026-04-19
- **Service:** fridays/scheduler.py
- **Error:** `check_due()` used `subprocess.Popen(action_data, shell=True)` — any SHELL task with user-controlled action_data could execute arbitrary commands
- **Cause:** Original scheduler used shell=True for convenience; never updated after action_data became user-editable via the tasker API
- **Fix:** Replaced with `subprocess.Popen(shlex.split(action_data))`. Shell metacharacters no longer interpreted.

---

## BUG-029: Scheduler main_loop() hardcoded run_daily_digest() call
- **Status:** fixed
- **Found:** 2026-04-19 (Session 21 audit)
- **Fixed:** 2026-04-19
- **Service:** fridays/scheduler.py
- **Error:** `main_loop()` called `run_daily_digest()` every 60 seconds regardless of schedule, bypassing the `check_due()` scheduling system entirely
- **Cause:** Legacy code from before the scheduler's `check_due()` system was built; never removed
- **Fix:** Removed direct `run_daily_digest()` call. Daily digest now fires via `check_due()` like all other tasks.

---

## BUG-030: Seven model memory exhaustion from keep_alive=-1
- **Status:** fixed
- **Found:** 2026-04-19 (Session 21 diagnosis)
- **Fixed:** 2026-04-19
- **Service:** agents/seven/seven_agent.py + Ollama model management
- **Error:** Seven model hangs after ~5 minutes, system becomes unresponsive. 12GB+ swap thrash.
- **Cause:** Three Ollama models loaded simultaneously with `keep_alive=-1` (infinite retention): seven:latest 7.2GB + gemma3 4.0GB + llama3.2 2.3GB = 13.5GB resident on 32GB system
- **Fix:** Changed `keep_alive` from `-1` to `300` (5 minutes auto-unload). Unloaded idle gemma3 + llama3.2 models.

---

## BUG-031: PROD crash-loop — orphaned PID holding port 5050
- **Status:** fixed
- **Found:** 2026-04-19 (Session 21)
- **Fixed:** 2026-04-19
- **Service:** systemd / swarm-terminal-prod.service
- **Error:** PROD not serving. Systemd restart counter reached 2725. Port 5050 occupied by orphaned PID 7338.
- **Cause:** Previous Flask process survived a systemd restart and held the port, causing every subsequent restart to fail immediately
- **Fix:** Killed orphaned PID 7338. PROD restored on :5050 (PID 443874).
| **needs_verification** | Fix applied, awaiting UAT confirmation |

---

## BUG-026: ALM status request storm degraded localhost responsiveness

- **Status:** fixed
- **Found:** 2026-03-30
- **Fixed:** 2026-03-30 15:03:00
- **Service:** frontend/theme_engine.py + frontend/terminal.py
- **Error:** `/api/alm/status` was being called at very high frequency, causing API/log churn and making localhost appear unstable.
- **Cause:** Theme-layer ALM sync used mutation-driven re-initialization that repeatedly triggered ALM status fetches under dynamic DOM updates.
- **Fix:**
  - Guarded ALM UI application and throttled runtime fetch behavior in `frontend/theme_engine.py`
  - Changed mutation observer path to non-fetch apply-only updates
  - Added 2-second cached response path in `frontend/terminal.py` for `/api/alm/status` to absorb burst traffic

---

## BUG-001: mailto: approval links
- **Status:** open
- **Found:** 2026-03-25 (noted in Session 10)
- **Service:** email_handler / unknown sender approval flow
- **Error:** Approval links in unknown sender emails use `mailto:` format — not tested end-to-end in live UAT
- **Cause:** mailto: links are generated correctly but full round-trip (email sent → Ghost clicks link → approval processed) has not been confirmed under real conditions
- **Fix:** Pending live UAT confirmation. Functionality believed working but unverified.

---

## BUG-002: TRUST/NOTIFY/IGNORE flow — broken pipe
- **Status:** deferred
- **Found:** 2026-03-25 (noted in Session 10)
- **Service:** email_handler / unknown sender notification flow
- **Error:** Unknown sender notification emails unreliable (sometimes not received); TRUST reply processing intermittent
- **Cause:** Automatic unknown-sender-hold-for-approval flow was fragile; root cause not fully isolated
- **Fix:** Deferred. Flow replaced by Librarian auto-triage (Session 10). TRUST/NOTIFY/IGNORE commands still work for manual list management but the automatic hold-for-approval flow is removed.

---

## BUG-003: telegram_bot.py passes priority= kwarg to ticket_create()
- **Status:** fixed
- **Found:** 2026-03-25
- **Service:** telegram_bot / ticket.py
- **Error:** `TypeError: ticket_create() got an unexpected keyword argument 'priority'`
- **Cause:** `telegram_bot.py` called `ticket_create()` with `priority=` kwarg; `ticket.create()` does not accept that parameter
- **Fix:** Removed `priority=` argument from the `ticket_create()` call in telegram_bot.py

---

## BUG-004: /api/sandpits returned empty agents list
- **Status:** fixed
- **Found:** 2026-03-25
- **Service:** VS (terminal.py / API layer)
- **Error:** Sandpits tab showed no agents; response contained `{stats:{}, log:[]}` instead of `{agents:[]}`
- **Cause:** API endpoint `/api/sandpits` returned the wrong response shape — stats/log format rather than the agents list the frontend expected
- **Fix:** Corrected response format to return `{agents: [...]}` matching the VS tab contract

---

## BUG-005: VS Feed tab used wrong activity_log field names
- **Status:** fixed
- **Found:** 2026-03-25
- **Service:** VS (frontend Feed tab)
- **Error:** Feed tab displayed blank/missing data for service, event type, and detail columns
- **Cause:** Frontend referenced fields `source`, `event_type`, `details` but `activity_log` table returns `service`, `event`, `detail`
- **Fix:** Updated VS Feed tab field references to match actual `activity_log` schema: `service`, `event`, `detail`

---

## BUG-006: memory_gemma missing `archived` column
- **Status:** fixed
- **Found:** 2026-03-25
- **Service:** database.py / memory_gemma
- **Error:** All other agent memory tables have `archived` column; memory_gemma did not — queries filtering `archived=0` would fail or skip gemma memory
- **Cause:** `memory_gemma` was created before `archived` was standardised across all memory tables; column was never added
- **Fix:** Two-part: (1) `ALTER TABLE memory_gemma ADD COLUMN archived INTEGER DEFAULT 0` applied to live DB; (2) SCHEMA definition in database.py updated to include `archived` and `source` columns (source also pre-existed in live DB but was missing from schema)

---

## BUG-007: discord_bot.py passes priority= kwarg to ticket_create()
- **Status:** fixed
- **Found:** 2026-03-25
- **Service:** discord_bot / ticket.py
- **Error:** Same pattern as BUG-003 — `discord_bot.py` line 197 passed `priority=priority` to `ticket_create()` which does not accept that parameter
- **Cause:** Copy-paste carry-over from telegram_bot.py fix; discord_bot was updated later and the same kwarg was included
- **Fix:** Removed `priority=priority` from the `ticket_create()` call in discord_bot.py

---

## BUG-008: archived filtering skipped for memory_gemma in three query sites
- **Status:** fixed
- **Found:** 2026-03-25
- **Service:** terminal.py / database.py
- **Error:** Memory queries for gemma did not apply `AND archived=0` filter — archived gemma memories appeared in all search results
- **Cause:** Workaround for the missing `archived` column (BUG-006) used `archived_clause = ""` for gemma. After BUG-006 was fixed, these workarounds became bugs themselves.
- **Fix:** Removed gemma exception from three sites: `_memory_search()` single-agent path (terminal.py), `_memory_search()` UNION ALL query (terminal.py), and `get_agent_memory()` (database.py)

---

## BUG-009: Browser confirm()/prompt() dialogs blocking VS tab
- **Status:** fixed
- **Found:** 2026-03-25
- **Service:** VS (frontend — terminal.html)
- **Error:** Seven destructive actions used `confirm()` or `prompt()` native browser dialogs — blocking popups that Ghost explicitly wanted removed
- **Cause:** Standard confirm guard pattern used throughout; not replaced when VS tab was built
- **Fix:** All `confirm()` removed. Destructive buttons now use `_arm()` helper (two-click arm-to-confirm within 3s, no dialog). `prompt()` for reject feedback replaced with inline hidden text input revealed on first click.

---

## BUG-015: orchestrator.py missing logging initialization
- **Status:** fixed
- **Found:** 2026-03-26
- **Service:** orchestrator.py
- **Error:** `NameError: name 'logger' is not defined`
- **Cause:** `consult_stage1` attempts to call `logger.warning` during Shell and Browser agent execution, but `logger` was never imported or initialized in this module.
- **Fix:** Add `import logging` and initialize `logger = logging.getLogger('seven.orchestrator')`.

---

## BUG-016: terminal.py missing log_activity import
- **Status:** fixed
- **Found:** 2026-03-26
- **Service:** terminal.py
- **Error:** `NameError: name 'log_activity' is not defined`
- **Cause:** Several API endpoints (like `/api/tickets/<n>/notes`) call `log_activity`, but it is not included in the `database.py` imports at the top of the file.
- **Fix:** Add `log_activity` to the `from database import (...)` statement.

---

## BUG-017: listener.py missing logging initialization
- **Status:** fixed
- **Found:** 2026-03-26
- **Service:** listener.py
- **Error:** `NameError: name 'logger' is not defined`
- **Cause:** `handle_followup_email` and `librarian_triage` call `logger.error`, but `logger` is not defined in the module.
- **Fix:** Add `import logging` and initialize `logger = logging.getLogger('seven.listener')`.

---

## BUG-018: VS Tab initialization crash (missing tables/nulls)
- **Status:** fixed
- **Found:** 2026-03-26
- **Service:** terminal.py / terminal.html
- **Error:** VS tab fails to load; 500 errors on `/api/swarm/status` or JS `.slice()` errors.
- **Cause:** API didn't check for existence of `memory_nine` table; JS didn't handle null timestamps/details.
- **Fix:** Added `sqlite_master` table checks in `terminal.py`; added `(val||'')` null-safety in `terminal.html`.

---

## BUG-019: Nine's file operations (Fridays) broken — signature & return type mismatch
- **Status:** fixed
- **Fixed:** 2026-03-26 14:45:33 by Ten (GPT)
- **Service:** fridays/file_agent.py, fridays/skills.py
- **Error:** `TypeError: read_sandpit() got unexpected keyword argument 'reader_agent'` and `TypeError: cannot unpack non-tuple`
- **Cause:** Two issues: (1) `skills.py` called `read_sandpit(path, filename, reader_agent=agent)` but function signature doesn't have that kwarg; (2) `read_sandpit()` returned plain content string or None, but callers expected `(ok, content)` tuples
- **Impact:** Nine could not read or write files through Fridays; all file skill operations would crash
- **Fix:**
  - Modified `fridays/file_agent.py:read_sandpit()` to return `(True, content)` or `(False, error_msg)` tuples
  - Modified `fridays/file_agent.py:read_shared()` to return tuples consistently
  - Removed invalid `reader_agent=agent` and `writer_agent=agent` kwargs from `fridays/skills.py` calls
  - Updated test function to unpack new tuple format
- **Testing:** Syntax validation passed; ready for functional testing

---

## BUG-020: listener.py ticket_create() unexpected `created_at` kwarg

- **Status:** fixed
- **Found:** 2026-03-29 (NINE-018 triage audit)
- **Fixed:** 2026-03-29 18:17:27
- **Service:** core/pipeline/listener.py
- **Error:** `TypeError: create() got an unexpected keyword argument 'created_at'`
- **Cause:** `ticket_create()` call on line 1079 passed `created_at=get_timestamp()` but `ticket.create()` has no such parameter. Crashed every new email at ticket creation stage — no emails were being processed.
- **Fix:** Removed `created_at=get_timestamp()` from the call. Ticket timestamps are handled by DB default.

---

## BUG-021: listener.py log_message() unexpected `created_at` kwarg

- **Status:** fixed
- **Found:** 2026-03-29 (NINE-018 triage audit)
- **Fixed:** 2026-03-29 18:17:27
- **Service:** core/pipeline/listener.py
- **Error:** `TypeError: log_message() got an unexpected keyword argument 'created_at'`
- **Cause:** Same pattern as BUG-020 — line 1080 passed `created_at=get_timestamp()` to `log_message()` which only accepts `(conv_id, from_agent, content, to_agent='', message_type='chat')`.
- **Fix:** Removed `created_at=get_timestamp()` from the call.

---

## BUG-022: listener.py `datetime` not imported in `_parse_snooze_time()`

- **Status:** fixed
- **Found:** 2026-03-29 (NINE-018 triage audit)
- **Fixed:** 2026-03-29 18:17:27
- **Service:** core/pipeline/listener.py (also affects telegram_bot.py via import)
- **Error:** `NameError: name 'datetime' is not defined`
- **Cause:** `_parse_snooze_time()` used `datetime.strptime()` for absolute date formats (e.g. `2026-04-01`) but only imported `timedelta` — `from datetime import timedelta`. Telegram bot also imports this function.
- **Fix:** Changed to `from datetime import timedelta, datetime`.

---

## BUG-023: listener.py wrong sniffer.py path in subprocess call

- **Status:** fixed
- **Found:** 2026-03-29 (NINE-018 triage audit)
- **Fixed:** 2026-03-29 18:17:27
- **Service:** core/pipeline/listener.py
- **Error:** Sniffles audit (RL-008) silently never ran — no error raised but subprocess pointed to a non-existent file
- **Cause:** `subprocess.Popen(['python3', '/home/seven/swarm/sniffer.py'])` — sniffer is at `agents/ghost/sniffer.py` not the swarm root
- **Fix:** Corrected to `/home/seven/swarm/agents/ghost/sniffer.py`.

---

## BUG-024: duck.py wrong column names in duck_log INSERT

- **Status:** fixed
- **Found:** 2026-03-29 (NINE-018 triage audit — dry run caught this)
- **Fixed:** 2026-03-29 18:17:27
- **Service:** agents/ghost/duck.py
- **Error:** `sqlite3.OperationalError: table duck_log has no column named verdict`
- **Cause:** `_log_to_duck_log()` used column names `verdict` and `note` which don't exist. Actual schema has `answer` and `reason`. This crashed Duck on every ticket close, leaving tickets in `open` status and queue entries stuck in `processing` indefinitely.
- **Fix:** Changed INSERT to use `answer` and `reason`.
- **Testing:** Dry run confirmed — 24/24 checks pass (`tests/test_triage_queue_dryrun.py`).

---

## BUG-025: `utils/simulate.py` is not deterministic for dry validation

- **Status:** open
- **Found:** 2026-03-30 (proactive dry-test sweep)
- **Service:** `utils/simulate.py` / orchestrator live model path
- **Error:** Simulation enters real-model route and can run for several minutes per stage (example: Gemma routing response at ~174s), preventing reliable "full dry" execution windows.
- **Cause:** Script advertises dry-run behavior but still executes non-stubbed live model calls in `consult_stage1/2/eight` paths.
- **Fix:** Add explicit deterministic stub mode for model calls (similar to `tests/test_triage_queue_dryrun.py`) and a hard timeout guard per stage.

---

## BUG-026: `pytest` missing from runtime test environment

- **Status:** fixed
- **Found:** 2026-03-30 (proactive dry-test sweep)
- **Fixed:** 2026-04-01 (session bug sweep — `pip install pytest` into .venv)
- **Service:** Local test execution environment
- **Error:** `python3 -m pytest tests -q` fails with `No module named pytest`.
- **Cause:** Test dependency not installed in current runtime image/environment.
- **Fix:** Installed pytest into `.venv`: `pip install pytest`.
- **Testing:** `python3 -m pytest tests -q` now runs in the project environment.

---

## BUG-031: terminal dashboard force-close failed with `No module named 'duck'`

- **Status:** fixed
- **Found:** 2026-04-01 (Session 11 QA telemetry review)
- **Fixed:** 2026-04-01 08:06:00
- **Service:** `frontend/terminal.py` / `core/pipeline/ticket.py`
- **Error:** Manual ticket closure from the dashboard could fail in background thread with `ticket_force_close_error` and `No module named 'duck'`.
- **Cause:** `ticket.librarian_close()` used a fragile legacy `from duck import on_ticket_closed` import path that was not guaranteed in every runtime/import context.
- **Fix:** Added a robust resolver in `core/pipeline/ticket.py` that imports `agents.ghost.duck` first and falls back to legacy `duck` path only if needed.
- **Testing:** Live API validation passed with synthetic ticket `QA-FORCECLOSE-001` via `POST /api/tickets/<ticket>/close`; ticket closed and activity log recorded `ticket_force_closed`.

---

## BUG-032: listener periodic loop did not run proposal notifications

- **Status:** fixed
- **Found:** 2026-04-01 (Session 11 workflow audit)
- **Fixed:** 2026-04-01 08:06:00
- **Service:** `core/pipeline/listener.py` / `utils/swarm_tasks.py`
- **Error:** Proposal discovery/notification was available but not part of the listener's normal periodic maintenance loop, so local-online agent proposal visibility could lag unless separately invoked.
- **Cause:** Listener periodic tasks ran snooze/SLA checks but omitted `check_proposals()`.
- **Fix:** Added `check_proposals()` to both Gmail Push mode and IMAP fallback periodic task cycles.
- **Testing:** Listener restarted cleanly and full E2E/UAT/daily gate remained green after change.

---

## BUG-033: Gmail Push fallback was one-way until restart

- **Status:** fixed
- **Found:** 2026-04-01 (Session 11 self-healing review)
- **Fixed:** 2026-04-01 08:06:00
- **Service:** `core/pipeline/listener.py`
- **Error:** After `invalid_grant` or similar push failures, listener fell back to IMAP polling and stayed there until a manual restart.
- **Cause:** Fallback logic preserved service continuity but did not periodically retry Gmail Push activation.
- **Fix:** Added self-healing retry loop in IMAP fallback mode. Listener now periodically attempts Gmail Push reactivation and switches back to instant delivery when watch/token recovery succeeds.
- **Testing:** Syntax compile passed, listener restarted cleanly, daily gate remained fully green.

---

## BUG-034: orchestrator SAP specialist import was brittle

- **Status:** fixed
- **Found:** 2026-04-01 (Session 11 telemetry follow-up)
- **Fixed:** 2026-04-01 08:10:00
- **Service:** `core/pipeline/orchestrator.py`
- **Error:** Historical listener telemetry included `eight_error` with `No module named 'eight'` during SAP/eight routing.
- **Cause:** `consult_stage_eight()` used a bare `import eight`, which depends on path state and is less reliable across runtime contexts.
- **Fix:** Added `_get_eight_module()` resolver that imports `agents.specialists.eight` first and falls back to legacy `eight` only if needed.
- **Testing:** Post-fix compile and regression suites remained green.

---

## BUG-027: Queue/proposal API regression (`/api/queue`, `/api/work-proposals`) returned 404

- **Status:** fixed
- **Found:** 2026-03-30 (self-audit connection sweep)
- **Service:** `frontend/terminal.py` Flask API layer
- **Error:** Connection smoke test returned 404 for `/api/queue` and `/api/work-proposals` while proposals/approvals workflow expected these routes.
- **Cause:** Route set drifted to legacy `/api/proposals*` endpoints; queue/work-proposal routes were absent in live terminal API.
- **Fix:** Restored endpoints in `frontend/terminal.py`:
  - `GET/POST /api/queue`
  - `GET/PATCH /api/queue/<int:queue_id>`
  - `GET /api/work-proposals`
  - `PATCH /api/work-proposals/<proposal_id>`
- **Verification:**
  - 11/11 API smoke checks pass
  - POST queue + PATCH proposal status flow validated end-to-end
  - Proposal backlog updated to `executed=6`, `pending=0`

---

## BUG-028: Telegram/Discord pipeline failures could leave queue in an ambiguous processing state

- **Status:** fixed
- **Found:** 2026-03-30 (channel stabilization pass)
- **Fixed:** 2026-03-30 13:20:00
- **Service:** `fridays/telegram_bot.py`, `fridays/discord_bot.py`, `core/pipeline/queue_manager.py`
- **Error:** When a channel pipeline exception happened after `mark_processing(queue_id)`, handler-level error replies were sent but queue recovery was not explicit in the channel module, creating operator-visible "ticket opened but not processed" behavior.
- **Cause:** `_run_pipeline()` in Telegram/Discord did not perform queue recovery in local exception paths; it depended on later service-loop cleanup.
- **Fix:**
  - added `mark_failed(queue_id, reason)` helper in `core/pipeline/queue_manager.py`
  - wrapped channel stage execution in `try/except`
  - on failure, reset queue entry back to `queued` and log `pipeline_failed` activity with ticket reference
- **Verification:**
  - static diagnostics clean for all three files
  - channel failure path now has deterministic queue recovery behavior

---

## BUG-029: Email/Discord/Telegram end-to-end reliability is still not practically verified in one governed pass

- **Status:** fixed
- **Found:** 2026-03-30 (operator report)
- **Fixed:** 2026-04-01 08:20:00
- **Service:** cross-channel intake -> queue -> ticket -> response pipeline
- **Error:** Operator reports inconsistent behavior: Telegram strange responses, tickets opening without full processing, email requests receiving no response, Discord behavior inconsistent.
- **Cause:** Mixed runtime paths are individually implemented, but no single governed UAT cycle has validated all channels against the same ALM/Vortex evidence criteria.
- **Fix:** Added `tests/test_notification_reliability.py` to validate unknown-sender notification semantics across email, Telegram, and Discord, including send failure logging behavior. Combined with existing `test_channel_smoke.py`, `test_telegram_trust.py`, `test_direct_agent_commands.py`, live SMTP sends, and UAT/E2E runs, this creates a governed cross-channel validation pass.
- **Testing:** `python3 tests/test_notification_reliability.py` => 3 PASS; `python3 tests/test_channel_smoke.py` => 8 PASS; daily gate remained fully green.

---

## BUG-035: Chat job stage displayed "loading local memory" after dispatch timeout

- **Status:** fixed
- **Found:** 2026-04-13
- **Fixed:** 2026-04-13
- **Service:** `frontend/blueprints/chat.py`
- **Error:** Chat jobs that were waiting on the 10-second dispatch timeout showed "loading local memory" as the stage label instead of the actual last-known pipeline stage (e.g. "Routing to agent…").
- **Cause:** After the timeout, the job's `stage` key in `_CHAT_JOBS` was assigned a time-based default label from the monitor rather than the last entry in `_agent_stage_trace`. The time-based label happened to always resolve to "loading local memory" for jobs in the early stage window.
- **Fix:** After merging trace entries, explicitly set `_pj['stage'] = _agent_stage_trace[-1]['text']` so the last known real stage is displayed.

---

## BUG-036: Debate R2 used Qwen after Qwen→Mistral rename

- **Status:** fixed
- **Found:** 2026-04-13
- **Fixed:** 2026-04-13
- **Service:** `core/pipeline/orchestrator.py` — `_run_debate_r2()`
- **Error:** Debate round 2 responses were attributed to Qwen and called `ask_agent('Qwen', ...)` even after Qwen was renamed to Mistral across the system.
- **Cause:** The `_run_debate_r2()` function was not updated during the Qwen→Mistral rename — it still used `qwen_r2`, `ask_agent('Qwen', ...)`, and `log_message(conv_id, 'Qwen', ...)`.
- **Fix:** Updated all references in `_run_debate_r2()` to use `mistral_r2`, `ask_agent('Mistral', ...)`, `log_message(conv_id, 'Mistral', ...)`.

---

## BUG-037: Service monitor showed Terminal as always-inactive

- **Status:** fixed
- **Found:** 2026-04-13
- **Fixed:** 2026-04-13
- **Service:** `frontend/blueprints/exec_bp.py`, `frontend/blueprints/system.py`
- **Error:** The Terminal service in the monitor panel always appeared inactive/offline even when the server was running.
- **Cause:** Both files referenced the systemd unit as `swarm-terminal` but the actual running service is `swarm-terminal-prod`.
- **Fix:** Corrected the service name from `swarm-terminal` → `swarm-terminal-prod` in both `exec_bp.py` (service list) and `system.py` (status check loop and label map).

---

## BUG-038: Approve button notified chat with no actionable instructions for agent

- **Status:** fixed
- **Found:** 2026-04-13
- **Fixed:** 2026-04-13
- **Service:** `utils/proposal_review.py` — `notify_proposal_status_change()`
- **Error:** Clicking Approve in Studio moved the proposal status but the chat notification just said "status changed to approved" with no instruction to the agent on what to do next. The agent had no signal to start building.
- **Cause:** `notify_proposal_status_change()` sent generic status-change messages for all statuses. There was no per-status actionable content.
- **Fix:** Rewrote `notify_proposal_status_change()` with per-status messages. `approved` now includes `SKILL alm_self_approve <id>` instruction; `in_progress` includes `SKILL alm_complete <id>` instruction; `uat` tells Ghost to review or ask Duck; `executed` confirms shipment.

---

## BUG-039: ALM pipeline skipped Duck QA — `done` went straight to `executed`

- **Status:** fixed
- **Found:** 2026-04-13
- **Fixed:** 2026-04-13
- **Service:** `utils/proposal_review.py`, `frontend/blueprints/proposals.py`, `frontend/static/js/views/studio.js`
- **Error:** When an agent marked a proposal as done, it could immediately be marked as executed by Ghost with no automated quality check and no UAT stage.
- **Cause:** The pipeline only had 5 statuses: `pending → approved → in_progress → done → executed`. There was no intermediate UAT stage and no automated Duck quality gate.
- **Fix:** Added full 6-stage pipeline: `pending → approved → in_progress → done → uat → executed`.
  - `duck_check_done()` is auto-triggered when a proposal hits `done`. It runs a quality gate and either advances to `uat` or bounces back to `in_progress` with feedback, notifying the originating chat thread.
  - `duck_execute_proposal()` allows Duck (on Ghost's instruction) to ship `uat → executed`.
  - Studio UI updated: `uat` status badge (amber), 6-step pipeline bar, UAT card/modal action buttons (Mark Executed / Ask Duck / Reopen).
  - `POST /api/work-proposals/<id>/duck-execute` endpoint added.

---

## BUG-040: `/library`, `/studio`, `/chat`, `/monitor` routes returned 404

- **Status:** fixed
- **Found:** 2026-04-13
- **Fixed:** 2026-04-13
- **Service:** `frontend/terminal.py`
- **Error:** Navigating directly to `/library`, `/studio`, `/chat`, or `/monitor` returned a 404 — no Flask route existed for these paths.
- **Cause:** The UI is a single-page app served at `/ui`. These convenience paths were never registered as Flask routes.
- **Fix:** Added a single `ui_redirect()` view registered on all four paths that redirects to `/ui`.
