# NINE-002: Memory Search Missing New Agent Tables + Delete Allowlist Incomplete

**Status**: PROPOSED
**Proposal ID**: NINE-002
**Proposed**: 2026-03-29
**Agent**: Nine (System Architect · Ghost Layer)
**Priority**: HIGH

---

## Issue

Two related gaps in `frontend/terminal.py`'s memory handling mean that Grok and Twelve's memories are invisible to the dashboard, and Ghost cannot delete memory entries from newer agent tables via the UI.

---

## Gap 1: `_memory_search()` UNION ALL Missing New Tables

`terminal.py:140-184` — the `_memory_search()` function builds a UNION ALL query across all agent memory tables. It currently covers:

```
memory, memory_llama, memory_qwen, memory_gemma, memory_eight, memory_nine, memory_ten
```

**Missing:**
- `memory_grok` — Grok (Agent 11) has **41 entries** in the DB. None are visible in the Memory tab.
- `memory_twelve` — Time Wizard (Agent 12) has entries. None visible.

The per-agent filter branch (`elif agent_key in (...)`) also only covers 5 agents and won't match 'grok' or 'twelve'.

**Impact**: Ghost searches memory from the dashboard and sees no results for Grok or Twelve. Memory tab is incomplete.

---

## Gap 2: `_ALLOWED_TABLES` in DELETE endpoint is stale

`terminal.py:366`:
```python
_ALLOWED_TABLES = {'memory', 'memory_llama', 'memory_qwen', 'memory_gemma', 'memory_eight'}
```

**Missing**: `memory_nine`, `memory_grok`, `memory_twelve`, `memory_ten`

If Ghost tries to delete a memory entry from Nine, Grok, Twelve, or Ten via the dashboard, the endpoint returns HTTP 400 "invalid table".

**Impact**: Ghost cannot manage memories for 4 of the active Ghost Layer agents from the dashboard.

---

## Root Cause

Both `_memory_search()` and `_ALLOWED_TABLES` were written during Sessions 1-9 when only the original 5 agent pools existed. Grok and Twelve were added later (Session 11/12) and the terminal.py memory layer was not updated.

Note: `utils/database.py` has its own `AGENT_POOL_MAP` that is up to date and knows about all agents. The local `_AGENT_TABLES` and `_ALLOWED_TABLES` in `terminal.py` are stale duplicates that diverge from the canonical source.

---

## Proposed Fix

### Fix 1: Add memory_grok and memory_twelve to `_memory_search()` UNION ALL

In `terminal.py`, extend the UNION ALL query to include:
```python
UNION ALL
SELECT id, 'memory_grok' AS source_table, agent, subject, content, tags, importance, created_at
FROM memory_grok
WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
  AND importance >= ? AND archived = 0
UNION ALL
SELECT id, 'memory_twelve' AS source_table, agent, subject, content, tags, importance, created_at
FROM memory_twelve
WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
  AND importance >= ? AND archived = 0
```
Also add `'grok'` and `'twelve'` to the `elif agent_key in (...)` branch of `_AGENT_TABLES`.

### Fix 2: Extend `_ALLOWED_TABLES`

```python
_ALLOWED_TABLES = {
    'memory', 'memory_llama', 'memory_qwen', 'memory_gemma',
    'memory_eight', 'memory_nine', 'memory_grok', 'memory_twelve', 'memory_ten'
}
```

### Longer-term (separate proposal): Centralise `_AGENT_TABLES`

The canonical source should be `AGENT_POOL_MAP` in `utils/database.py`. `terminal.py` should import and derive from it rather than maintaining its own copy. Prevents this divergence happening again.

---

## Files to Change

| File | Lines | Change |
|------|-------|--------|
| `frontend/terminal.py` | 101-111 | Add grok, twelve to `_AGENT_TABLES` |
| `frontend/terminal.py` | 140-184 | Add UNION ALL for memory_grok, memory_twelve |
| `frontend/terminal.py` | 366 | Add missing tables to `_ALLOWED_TABLES` |

~25 lines total.

---

## Testing Plan

- [ ] Search memory for "grok" in dashboard → Grok's 41 entries visible
- [ ] Search memory with agent filter "twelve" → Twelve's entries visible
- [ ] `DELETE /api/memory/<id>?table=memory_nine` → returns 200, not 400
- [ ] `DELETE /api/memory/<id>?table=memory_grok` → returns 200, not 400
- [ ] `DELETE /api/memory/<id>?table=memory_twelve` → returns 200, not 400

---

## Risk Assessment

- **Risk Level**: LOW ✅
- **Impact**: Read-only query extension + whitelist expansion. No data mutation. No schema changes.
- **Rollback**: Revert the ~25 line edits.

---

## Dependencies

- None. Standalone fix.
- Related: NINE-005 (sonic/scholar/seeker tables don't exist yet — don't add those here)

---

## Proposed by Nine

Discovered during full codebase audit, 2026-03-29.
Verified by cross-referencing AGENT_POOL_MAP in utils/database.py against _AGENT_TABLES in terminal.py.
Confirmed memory_grok has 41 entries via swarm_memory.db table count in AUDIT_V3_MARCH_28.md.
