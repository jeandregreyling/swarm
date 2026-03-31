# NINE-022 — Session 5 Full System Audit

**Agent**: Nine (System Architect · Ghost Layer)
**Date**: 2026-03-31
**Status**: EXECUTED
**Priority**: HIGH
**Decision ID**: 102 (decisions table)

---

## Scope

Full audit of `/home/seven/swarm` covering:

- Python syntax/import errors (`py_compile` on all .py files in frontend/, utils/, agents/, core/, fridays/)
- Flask route conflict check (terminal.py duplicate function names / method overlaps)
- Database schema — SCHEMA constant vs live DB via PRAGMA table_info
- Agent files — grok_agent.py, twelve_agent.py, imports, error handling
- Theme pipeline — fridays.json keys vs CSS var usage in templates
- Queue/proposals — queue_manager.py intake_internal(), work_proposals schema
- change_logger.py — sys.path and all function signatures
- HTML templates — broken JS, undefined functions, missing element IDs

---

## Findings

### Clean (no bugs)

- All 30+ .py files compile with no syntax errors
- Flask route "duplicates" are legitimate REST patterns — different HTTP methods per URL, no real conflict
- Modal IDs (`ticket-detail-modal`, `chat-detail-modal`, etc.) are dynamically created via `document.createElement` — not missing HTML elements
- `change_logger.py` sys.path correct, all exported functions present
- `grok_agent.py` — imports, error handling, context building all correct
- `twelve_agent.py` — imports, error handling, DB queries all valid against live schema
- `queue_manager.py` `intake_internal()` — schema correct, work_proposals insert valid
- `fridays.json` — all keys present, time_of_day palettes complete

### Bugs Fixed

#### BUG-A — change_logger.py mark_executed() broken subquery

**File**: `utils/change_logger.py`
**Severity**: HIGH — data corruption risk
**Description**: The `mark_executed()` function contained a subquery that matched every pending
`work_proposals` row with `queue_id > 0`, causing ALL pending proposals to be marked `executed`
whenever any single decision was marked PASS. This silently corrupted proposal state across the
entire swarm with no traceability.

**Fix**: Replaced the catch-all subquery with a targeted match on `proposal_file`, scoping the
update to only the work_proposal whose `proposal_file` matches the decision being executed.

```python
# Before (BROKEN — matches ALL pending proposals):
WHERE status='pending' AND queue_id IN (
    SELECT queue_id FROM work_proposals WHERE queue_id > 0
)

# After (FIXED — scoped to this decision's proposal_file):
WHERE status='pending' AND proposal_file = (
    SELECT proposal_file FROM decisions WHERE decision_id=?
) AND proposal_file != ''
```

---

#### BUG-B — database.py SCHEMA daily_checkpoint wrong columns

**File**: `utils/database.py`
**Severity**: MEDIUM — fresh install breakage
**Description**: The `SCHEMA` constant defined `daily_checkpoint` with columns:
`id, checkpoint_date, agent, summary, ticket_count, memory_count, decisions_count, created_at`

The live database has a completely different schema:
`checkpoint_id, timestamp, codebase_hash, memory_state, decisions_count, description, is_stable`

`twelve_agent.py` queries `timestamp`, `description`, `decisions_count`, `checkpoint_id` — all of
which only exist in the live schema. A fresh install would have created the wrong table and caused
`twelve_agent.py` to fail on every context build.

**Fix**: Updated SCHEMA constant to match the live DB schema.

---

#### BUG-C — ghost_briefs and scheduled_tasks missing from SCHEMA and _migrate_schema

**File**: `utils/database.py`
**Severity**: MEDIUM — fresh install breakage
**Description**: Two tables used by production code were absent from both the SCHEMA constant and
the `_migrate_schema()` migration loop:

- `ghost_briefs` — used by `utils/brief_engine.py` (INSERT and SELECT calls)
- `scheduled_tasks` — referenced in `utils/create_docs.py` documentation

Both tables exist in the live DB but would not be created on a fresh install, causing
`brief_engine.py` to fail with `OperationalError: no such table`.

**Fix**: Added both tables to SCHEMA constant and to the `_migrate_schema()` migration loop with
correct column definitions matching the live DB.

---

#### BUG-D — CSS vars undefined in terminal_base.html fallback :root

**File**: `frontend/templates/terminal_base.html`
**Severity**: LOW-MEDIUM — visual breakage on floating windows
**Description**: Four CSS custom properties were referenced in floating window styles but had no
fallback value defined in the `:root` block or in `fridays.json`:

- `--danger` — used for close button hover background (`.window-btn.close:hover`)
- `--shadow` — used for floating window drop shadow (`.floating-window box-shadow`)
- `--glass-blur` — used for backdrop blur effect (`.floating-window backdrop-filter`)
- `--glass-opacity` — used for window opacity (`.floating-window opacity`)

Without these, browsers render undefined vars as empty strings — causing no shadow, no glass
blur, invisible opacity value (defaults to 1 in CSS, so opacity was benign but wrong).

**Fix**: Added fallback values to the `:root` block:
```css
--danger:        #e03c3c;
--shadow:        0 8px 32px rgba(0,0,0,0.5);
--glass-opacity: 1;
--glass-blur:    0px;
```

---

## Validation

- All fixed Python files pass `py_compile`
- `initialise_database()` runs clean — all tables created/verified including ghost_briefs and scheduled_tasks
- Server restarted with fixes applied; `/api/queue` responds correctly
- CSS var fallbacks verified present in `:root` block

---

## DB Entries

- `decisions` table: `decision_id=102`, `agent=nine`, `test_status=PASS`, `commit_hash=audit-session5`
- `work_proposals` table: `proposal_id=NINE-022`, `status=executed`
