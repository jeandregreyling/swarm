# NINE-005: memory_sonic / memory_scholar / memory_seeker Tables Missing from DB

**Status**: EXECUTED
**Proposal ID**: NINE-005
**Proposed**: 2026-03-29
**Agent**: Nine (System Architect · Ghost Layer)
**Priority**: MEDIUM — Silent failure risk for future agents

---

## Issue

Three new Ghost Layer agents (Sonic, Scholar, Seeker) appear in `_AGENT_ROSTER` in `terminal.py` and in `AGENT_POOL_MAP` in `utils/database.py`, but their memory tables **do not exist** in `swarm_memory.db`.

---

## Evidence

### In `utils/database.py` — AGENT_POOL_MAP:
```python
AGENT_POOL_MAP = {
    ...
    'sonic':   'memory_sonic',    # ← referenced
    'scholar': 'memory_scholar',  # ← referenced
    'seeker':  'memory_seeker',   # ← referenced
}
```

### In `utils/database.py` — SCHEMA (lines 141-175):
The schema **does define** CREATE TABLE IF NOT EXISTS for memory_sonic, memory_scholar, memory_seeker.

### In `swarm_memory.db` — Actual tables:
```
memory_grok ✅
memory_twelve ✅
memory_nine ✅
memory_sonic   ❌ MISSING
memory_scholar ❌ MISSING
memory_seeker  ❌ MISSING
```

The `database.py` schema includes these tables but they were never initialised. This happens when `database.py` was not re-run after the schema was updated to include the new agents.

---

## Risk

Any code that calls `save_agent_memory('sonic', ...)` or similar will:
- Attempt an INSERT into a non-existent table
- Raise `sqlite3.OperationalError: no such table: memory_sonic`
- Fail silently (depending on exception handling) or crash the calling service

The agents are visible in the dashboard roster but have no functional memory backing. If any agent pipeline ever routes to Sonic/Scholar/Seeker, it breaks.

---

## Proposed Fix

**Re-run the schema initialisation** to create the missing tables. The SCHEMA constant in `database.py` already has the correct `CREATE TABLE IF NOT EXISTS` statements — they just haven't been executed against the live DB.

**Method**: Run the database initialisation script:
```bash
cd /home/seven/swarm && python3 utils/database.py
```

This runs `_init_db()` which executes all CREATE TABLE IF NOT EXISTS statements. It is idempotent — existing tables are untouched. Only the three missing tables will be created.

**Alternative**: Execute directly via sqlite3:
```sql
-- From swarm_memory.db:
CREATE TABLE IF NOT EXISTS memory_sonic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'sonic',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 5,
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
-- (same pattern for memory_scholar, memory_seeker)
```

---

## Secondary Issue: Agent Models Not Yet Wired

The three agents are listed in `_AGENT_ROSTER` with models:
- Sonic: `claude-3-5-sonnet` — this is an older Claude model name (correct model ID: `claude-3-5-sonnet-20241022`)
- Scholar: `gemini-2.0-flash` — Gemini API not wired
- Seeker: `tavily-search` — Tavily integration exists in `lib/search/internet_tavily.py` but not as a conversational agent

These agents are currently placeholders in the roster. The DB table creation (above) is the foundation step. API wiring is a separate, future proposal.

---

## Files to Change

| Action | Location |
|--------|----------|
| Run `python3 utils/database.py` | Creates 3 missing tables |
| No code changes needed | Schema already correct |

---

## Testing Plan

- [ ] `python3 utils/database.py` completes without error
- [ ] `sqlite3 swarm_memory.db ".tables"` shows memory_sonic, memory_scholar, memory_seeker
- [ ] `sqlite3 swarm_memory.db "SELECT COUNT(*) FROM memory_sonic"` → 0 (empty, but exists)
- [ ] `python3 -c "from utils.database import save_agent_memory; save_agent_memory('sonic', 'test', 'test content')"` → no error

---

## Risk Assessment

- **Risk Level**: VERY LOW ✅
- `CREATE TABLE IF NOT EXISTS` is fully idempotent.
- No data mutation. No service restart needed.
- No code changes required.

---

## Dependencies

- None. This is a one-command fix.
- Related: NINE-002 (once tables exist, add them to memory search if needed)

---

## Proposed by Nine

Discovered during full codebase audit, 2026-03-29.
Verified by querying `.tables` output from swarm_memory.db and cross-referencing with AGENT_POOL_MAP and database.py SCHEMA.
