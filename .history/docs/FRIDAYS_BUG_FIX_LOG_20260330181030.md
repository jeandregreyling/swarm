# Fridays Bug Audit & Fixes - March 28, 2026
**Agent Twelve - Refinement Phase Test Log**

---

## Overview
- **Total Bugs Found:** 26
- **Severity Breakdown:** 5 CRITICAL, 10 HIGH, 11 MEDIUM  
- **Estimated Fix Time:** ~14 hours
- **Test Status:** IN PROGRESS

---

## CRITICAL BUGS (5) - Must Fix First

### BUG-001: `/api/hands/run` endpoint missing
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py, frontend/templates/terminal_ui_v2.html
- **Issue:** JavaScript calls `/api/hands/run` but endpoint doesn't exist
- **Expected:** POST to `/api/hands/run` with `{command: "..."}`
- **Test:** Call `/api/hands/run` with `whoami` command
- **Fix Required:** Create endpoint or redirect to `/api/shell/execute`

### BUG-002: `/api/monitor` returns wrong schema
- **Status:** ❌ NOT FIXED  
- **File:** frontend/terminal.py:1214, terminal_ui_v2.html:1152
- **Issue:** Returns wrong field names (cpu_percent vs system_load, etc.)
- **Expected:** `{system_load, memory_usage, agents_online, pending_tasks}`
- **Actual:** `{ram_used_gb, ram_total_gb, cpu_percent, ...}`
- **Test:** GET `/api/monitor` and verify field names match frontend expectations
- **Fix Required:** Map returned fields to expected names

### BUG-003: `/api/agents/memories/query` returns wrong schema  
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:2180, terminal_ui_v2.html:1118
- **Issue:** Returns flat array instead of grouped-by-agent object
- **Expected:** `{results: {gemma: [...], llama: [...]}}`
- **Actual:** `{entries: [...], agent: "...", ...}`
- **Test:** Call `/api/agents/memories/query?q=test` and check structure
- **Fix Required:** Restructure response to group by agent

### BUG-004: Terminal commands endpoint path mismatch
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py (needs `/api/hands/run`), frontend/templates/terminal_ui_v2.html:979
- **Issue:** Frontend calls `/api/hands/run`, backend implements `/api/shell/execute`
- **Test:** Execute command from Terminal tile, verify it runs
- **Fix Required:** Add `/api/hands/run` endpoint that delegates to shell_execute

### BUG-005: No error handling in chat endpoint
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:1359-1430
- **Issue:** Missing error handling; frontend gets stuck on agent failures
- **Test:** Send chat message, verify response includes error handling
- **Fix Required:** Add try/except with proper error responses

---

## HIGH SEVERITY BUGS (10)

### BUG-006: `/api/docs` endpoint schema mismatch
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:863
- **Test:** GET `/api/docs` and verify response is array of {filename, description, size}

### BUG-007: Agent roster ghost_layer field inconsistency
- **Status:** ✅ PARTIALLY FIXED (commit df11769)
- **File:** frontend/terminal.py:1321
- **Test:** GET `/api/agents` and verify `ghost_layer` exists and is boolean

### BUG-008: Memory endpoint missing response wrapper
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:2043
- **Test:** GET `/api/agents/gemma/memory` and check for `entries` field

### BUG-009: REST path inconsistency - memories/query
- **Status:** ❌ NOT FIXED  
- **File:** frontend/terminal.py (no `/api/agents/memories/query` endpoint)
- **Test:** Call `/api/agents/memories/query?q=test`, should not return 404

### BUG-010: Ticket detail brittle message retrieval
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:277-280
- **Test:** GET `/api/tickets/1001/messages` and verify it returns history

### BUG-011: Chat endpoint missing actual response  
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:1359-1430
- **Test:** POST `/api/chat` with message, verify response includes agent output

### BUG-012: Studio endpoint incomplete
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:335-350
- **Test:** GET `/api/studio` returns complete agent details

### BUG-013: Memory limit parameter unbounded
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py multiple memory endpoints
- **Test:** Call with `?limit=9999` and verify reasonable cap applied

### BUG-014: Ticket close async without status tracking
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:707-742
- **Test:** Close ticket, poll status, verify eventual completion

### BUG-015: Memory table schema inconsistency
- **Status:** ✅ PARTIALLY FIXED (commit df11769)
- **File:** frontend/terminal.py:_memory_search()
- **Test:** GET `/api/memory` with various agents, all should return `subject` field

---

## MEDIUM SEVERITY BUGS (11)

### BUG-016: API 404 handling inconsistent
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py (multiple endpoints)
- **Test:** Request non-existent resource, verify consistent error response

### BUG-017: Agent temperature validation missing
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:1346-1358
- **Test:** Try to set temperature for non-existent agent, should reject

### BUG-018: Time Machine integration unused
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py (imported but never used)
- **Test:** Send time-sensitive question, verify context included

### BUG-019: Proposal approval no validation
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:472-525
- **Test:** Approve proposal with invalid agent, should reject

### BUG-020: Duck log missing null check
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:298-303
- **Test:** Request ticket detail, duck result should handle missing case

### BUG-021: Snoozed tickets missing import
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:558-577
- **Test:** Snooze a ticket, verify timezone parsing works

### BUG-022: Project docs SQL injection risk
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:929-950
- **Test:** Seed docs, verify no injection possible

### BUG-023: Kill switch state not persisted
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:60-66
- **Test:** Toggle agent offline, restart service, verify state persists

### BUG-024: Activity log duplicate reverse logic
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:1285, 1298
- **Test:** Stream activity, verify order is chronological

### BUG-025: Agent temperature null handling
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:1321-1332
- **Test:** All agents should show valid temperature in /api/agents

### BUG-026: Nine/Claude API key error handling
- **Status:** ❌ NOT FIXED
- **File:** frontend/terminal.py:1706-1791
- **Test:** Call without API key, should fail gracefully with clear message

---

## Fix Priority Order

1. **CRITICAL (Must complete before Claude review):**
   - BUG-001: Add `/api/hands/run` endpoint ← START HERE
   - BUG-002: Fix `/api/monitor` schema
   - BUG-003: Fix `/api/agents/memories/query` structure
   - BUG-004: Terminal commands working
   - BUG-005: Chat error handling

2. **HIGH (Should complete before Claude review):**
   - BUG-006 through BUG-015

3. **MEDIUM (Nice to have, document if skipped):**
   - BUG-016 through BUG-026

---

## Testing Template

Each bug when fixed should have:
```
### BUG-XXX: [Title]
- **Status:** ✅ FIXED
- **Commit:** [hash]
- **Changed Files:** [list]
- **Test Result:** 
  - [Test case 1]: PASSED ✅
  - [Test case 2]: PASSED ✅
- **Verification:** [curl/endpoint validation]
```

---

## Change Log

### BUG-VTX-DRYRUN-LEGACY-SCHEMA: Vortex dry-run failed on legacy checkpoints
- **Status:** ✅ FIXED
- **Date:** 2026-03-30
- **Files:**
   - `core/time_machine.py`
   - `frontend/terminal.py`
- **Root Cause:**
   - Legacy checkpoint payloads (example: `system_bootstrap`) stored scalar counters like `decisions: 3` instead of list snapshots.
   - `preview_restore()` / `restore_workflow_state()` assumed iterable lists and raised `TypeError: 'int' object is not iterable`.
   - Frontend process intermittently booted with shadow module `lib/system/time_machine.py`, preventing consistent Vortex route behavior.
- **Fix Applied:**
   - Added workflow state normalization in `TimeMachine._normalize_workflow_state()` to coerce legacy schemas into stable list+count shape.
   - Added ALM/audit mirroring via `TimeMachine._write_activity_log()` so checkpoint/dry-run/restore operations are written to `activity_log` (`service='vortex'`).
   - Pinned terminal import path to core Vortex implementation via explicit importlib load in `frontend/terminal.py` and `sys.modules['time_machine']` override.
- **Dry-Test Results:**
   - Matrix dry-run across latest checkpoints: **OK 20 / FAIL 0**.
   - Legacy checkpoint verification (`system_bootstrap`) via live API: **ok=True, dry_run=True**.
   - Persistent audit evidence present in `activity_log`: events `restore_preview`, `checkpoint_created`, `restore_applied` under `service='vortex'`.
- **ALM/Audit Outcome:**
   - Dry-run and restore preview now produce deterministic, persisted audit trail suitable for ALM review.
   - Vortex can now step through legacy and current checkpoints without schema crash.

### BUG-VTX-THEME-SHADOW-IMPORT: Theme layer not pinned to core TimeMachine
- **Status:** ✅ FIXED
- **Date:** 2026-03-30
- **File:** `frontend/theme_engine.py`
- **Issue:** Theme-engine data baking (`get_time_wizard_data`, `get_alm_data`) imported `time_machine` via mutable path insertion, which could resolve to legacy module in mixed-runtime states.
- **Fix:** Added `_get_core_time_wizard()` with explicit importlib load from `core/time_machine.py` and applied it to both theme-layer data paths.
- **Validation:** Runtime check shows `tw_ok=True`, `alm_ok=True`, `status=enforced`, `time_wizard_active=True` after frontend restart.

