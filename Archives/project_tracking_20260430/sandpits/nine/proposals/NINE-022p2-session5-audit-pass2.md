# NINE-022p2 — Session 5 Pass 2 Full System Audit

**Agent**: Nine (System Architect · Ghost Layer)
**Date**: 2026-03-31
**Status**: EXECUTED
**Priority**: HIGH
**Decision ID**: 104

---

## Summary

Second full system audit pass. All Python files in frontend/, utils/, agents/, core/, fridays/
compiled clean. Flask routes verified with method-aware analysis (118 unique route+method combos,
zero true duplicates). DB schema audited against live swarm_memory.db for all 49 tables. HTML
templates checked for broken JS references and missing element IDs. 4 real bugs found and fixed.

---

## Bugs Fixed

### BUG-E — database.py SCHEMA: time table column drift
**File**: `utils/database.py`
**Severity**: Medium (breaks fresh installs; live DB unaffected due to time_machine.py migration)

The SCHEMA string and `_migrate_schema` fallback loop both defined `time_events`, `time_journal`,
and `time_checkpoints` with OLD column names that don't match the live DB (which was created by
`core/time_machine.py`'s `init_schema()`):

| Table            | SCHEMA had                        | Live DB has                                        |
| ---------------- | --------------------------------- | -------------------------------------------------- |
| time_events      | description, metadata             | timestamp, action, target, state_hash, details     |
| time_journal     | entry, tags                       | timestamp, session_id, phase, status, notes        |
| time_checkpoints | name (UNIQUE), state_snapshot     | checkpoint_name (UNIQUE), timestamp, full_state    |

**Fix**: Updated both the SCHEMA string and `_migrate_schema` fallback DDL to use the live-DB column
names. `time_machine.py`'s `_migrate_compat_schema()` bridges old->new at runtime, so existing
deployments are unaffected. Fresh installs now create the correct schema from the start.

---

### BUG-F — database.py _migrate_schema: approval_tokens fallback DDL stale
**File**: `utils/database.py`
**Severity**: Medium (breaks fresh installs that hit the fallback path)

The `_migrate_schema` fallback for `approval_tokens` (runs if the table doesn't exist) created it
with the OLD schema `(pending_email_id INTEGER, used INTEGER DEFAULT 0)`. The production code in
`use_approval_token()` queries `WHERE token=? AND status='pending'` and updates `SET status='used',
used_at=datetime('now')` — columns that don't exist in the stale DDL.

SCHEMA (which runs before `_migrate_schema`) creates the correct table, so existing deployments are
safe. But the stale fallback means any environment that somehow missed the SCHEMA run would create a
broken table.

**Fix**: Updated `_migrate_schema` fallback to match the SCHEMA and live DB:
`(token, action, target_email, created_by, created_at, used_at, status)`.

---

### BUG-G — terminal.py: /api/health endpoint missing
**File**: `frontend/terminal.py`
**Severity**: Low (health checks return 404; logged in /tmp/swarm_terminal.log at startup)

No `/api/health` route existed. The server log showed a 404 on `GET /api/health` at startup
(20:01:54 in the current run). Service monitors, load balancers, and uptime checkers hitting this
endpoint get a 404 and may falsely report the service as down.

**Fix**: Added `GET /api/health` route before the `@app.route('/')` handler:
```python
@app.route('/api/health')
def api_health():
    """Lightweight health check endpoint. Returns 200 if server is up."""
    return jsonify({'ok': True, 'status': 'up', 'service': 'swarm-terminal'})
```

---

### BUG-H — lib/search/internet.py: hard ddgs import with no fallback
**File**: `lib/search/internet.py`
**Severity**: Low (runtime works via PYTHONPATH; breaks in clean environments)

`internet.py` did a hard `from ddgs import DDGS` at module level with no try/except. The `ddgs`
package is installed in `/home/seven/.local/lib/python3.12/site-packages/` and loaded via the
running server's `PYTHONPATH` env var — but is not in the venv and not system-installed. Any process
launched without that PYTHONPATH (e.g., tests, CI, fresh shell) would get a `ModuleNotFoundError`
on `import orchestrator` (which imports `internet`) and crash the entire orchestrator load.

**Fix**: Replaced hard import with try/except chain:
1. Try `from ddgs import DDGS`
2. Fall back to `from duckduckgo_search import DDGS`
3. If both fail, set `_DDGS_OK = False` and make `search_web()` return a graceful error string
   instead of crashing.

---

## Files Changed

| File                          | Change                                                    |
| ----------------------------- | --------------------------------------------------------- |
| `utils/database.py`           | SCHEMA time table columns updated; _migrate_schema fixed  |
| `frontend/terminal.py`        | /api/health route added                                   |
| `lib/search/internet.py`      | ddgs import hardened with try/except fallback             |

---

## Validation

- All 3 changed files pass `python3 -m py_compile`
- DB schema verified: live DB columns match SCHEMA after fix
- `/api/health` route confirmed registered in Flask route table
- `internet.py` imports cleanly in both ddgs-present and ddgs-absent environments

---

## No Bugs Found (this pass)

- All Python files in frontend/, utils/, agents/, core/, fridays/ compile clean
- Flask route method analysis: 118 unique route+method combos, zero true duplicates
- Modal IDs (`chat-detail-modal`, `ticket-detail-modal`, `window-help-modal`) are dynamically
  created via `document.createElement` in JS — not missing from HTML
- `studio-btn-` is correct dynamic ID construction (`'studio-btn-' + agent`)
- `change_logger.py` sys.path and all function signatures valid
- `grok_agent.py` and `twelve_agent.py`: imports, error handling, DB queries all correct
- `fridays.json` keys match all usages in theme_engine.py and templates
- `queue_manager.py` `intake_internal()` and `work_proposals` schema aligned
