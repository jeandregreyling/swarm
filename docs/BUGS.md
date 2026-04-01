# BUGS — Seven's Swarm Canonical Bug Log

<!-- markdownlint-disable -->

_Maintained by Nine (Ghost Layer). Last updated: 2026-03-30 10:05:00 (Session 5 proactive dry-run + approvals audit)._

---

## Legend

| Status | Meaning |
|--------|---------|
| **open** | Confirmed bug, not yet resolved |
| **deferred** | Won't fix in this phase |
| **fixed** | Resolved and tested |
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
- **Fixed:** 2026-03-26 14:45:33 by Copilot
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
- **Fix:** Installed pytest into `.venv`: `pip install pytest`. Full test suite runs 16 PASS 0 FAIL.

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

- **Status:** open
- **Found:** 2026-03-30 (operator report)
- **Service:** cross-channel intake -> queue -> ticket -> response pipeline
- **Error:** Operator reports inconsistent behavior: Telegram strange responses, tickets opening without full processing, email requests receiving no response, Discord behavior inconsistent.
- **Cause:** Mixed runtime paths are individually implemented, but no single governed UAT cycle has validated all channels against the same ALM/Vortex evidence criteria.
- **Fix:** Execute the expanded channel reliability UAT suite and log pass/fail evidence with proposal lifecycle + Vortex timeline checkpoints.
