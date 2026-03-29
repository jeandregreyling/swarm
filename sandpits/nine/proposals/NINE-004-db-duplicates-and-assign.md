# NINE-004: Clean Duplicate Agent DB Entries + Fix assign_ticket Stale Agent Names

**Status**: EXECUTED
**Proposal ID**: NINE-004
**Proposed**: 2026-03-29
**Agent**: Nine (System Architect · Ghost Layer)
**Priority**: MEDIUM

---

## Issue A: Duplicate Agent Entries in DB

The `agents` table in `swarm_memory.db` has 15 entries but only 11 distinct agents. Four agents exist in both capitalised (legacy, 2026-03-19) and lowercase (current) forms:

| Lowercase (current) | Capitalised (legacy) | Created |
|---------------------|---------------------|---------|
| gemma | Gemma | 2026-03-19 |
| llama | LLaMA | 2026-03-19 |
| qwen | Qwen | 2026-03-19 |
| librarian | Librarian | 2026-03-19 |

The orchestrator has used lowercase agent names since commit 686bac6 (`AGENTS = {'gemma': ...}`). The capitalised rows are dead. Nothing routes to them.

**Impact**:
- The `/api/agents` endpoint returns the hardcoded `_AGENT_ROSTER` from terminal.py (not the DB), so the duplicate rows don't cause UI issues — but they create noise in any raw DB query and in the AUDIT_V3 report which flags them as "duplicates needing cleanup".
- Any future code that queries the `agents` table directly (e.g., status checks, stats) may double-count.

---

## Issue B: `assign_ticket` Uses Capitalised Agent Names

`frontend/terminal.py:682`:
```python
_valid_agents = {'Gemma', 'LLaMA', 'Qwen', 'Eight', 'Librarian'}
```

Problems:
1. **Capitalised** — immediately contradicted by line 704: `routing['agents'] = agent.lower()`. Inconsistent.
2. **Stale** — doesn't include newer agents Nine, Grok, Twelve that exist in the roster and could be valid assignment targets.
3. **Librarian** — Librarian does not run pipeline responses; it only tags/indexes. Assigning a ticket to Librarian doesn't make operational sense.

---

## Proposed Fix A: Delete Legacy Capitalised Agent Rows

SQL to execute (one-time migration, can be run via dashboard or directly):

```sql
DELETE FROM agents WHERE name IN ('Gemma', 'LLaMA', 'Qwen', 'Librarian');
```

No Python changes needed. The `_seed_agents()` function in `utils/database.py` uses `INSERT OR IGNORE` with lowercase names, so re-running it after cleanup will not re-insert the old capitalised rows.

---

## Proposed Fix B: Update `assign_ticket` Valid Agents

```python
# frontend/terminal.py:682 — replace:
_valid_agents = {'Gemma', 'LLaMA', 'Qwen', 'Eight', 'Librarian'}

# with:
_valid_agents = {'gemma', 'llama', 'qwen', 'eight'}
# Note: Librarian removed (indexer only, cannot answer tickets)
# Note: Nine/Grok/Twelve not included — they don't run the standard pipeline
# Note: All lowercase to match routing system
```

Also remove the now-unnecessary `.lower()` call at line 704 since the set already contains lowercase values — or keep it as a safety net (harmless either way).

---

## Files to Change

| Action | Location | Change |
|--------|----------|--------|
| SQL DELETE | `swarm_memory.db` | Remove 4 capitalised agent rows |
| Code fix | `frontend/terminal.py:682` | Update `_valid_agents` to lowercase set |

---

## Testing Plan

- [ ] `sqlite3 swarm_memory.db "SELECT name FROM agents"` → only lowercase names remain
- [ ] `sqlite3 swarm_memory.db "SELECT COUNT(*) FROM agents"` → 11 rows (was 15)
- [ ] POST to `/api/tickets/TICKET-1/assign` with `{"agent": "gemma"}` → 200 OK
- [ ] POST to `/api/tickets/TICKET-1/assign` with `{"agent": "Gemma"}` → 400 (correctly rejected — old format no longer valid)
- [ ] POST to `/api/tickets/TICKET-1/assign` with `{"agent": "librarian"}` → 400 (correctly rejected)

---

## Risk Assessment

- **Risk Level**: LOW ✅
- The DB deletion removes dead rows that nothing reads.
- The `assign_ticket` fix is a validation tightening — no functional change to existing code paths that send lowercase agent names.
- `_seed_agents()` uses `INSERT OR IGNORE` so it's safe to re-run after the cleanup.

---

## Dependencies

- None.

---

## Proposed by Nine

Discovered during full codebase audit, 2026-03-29.
Verified by AUDIT_V3_MARCH_28.md which explicitly lists "15 agents (10 active, 5 duplicates)" and flags cleanup as needed.
