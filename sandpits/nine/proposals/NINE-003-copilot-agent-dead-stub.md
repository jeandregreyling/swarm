# NINE-003: copilot_agent.py is a Dead Stub — Remove or Wire It

**Status**: PROPOSED
**Proposal ID**: NINE-003
**Proposed**: 2026-03-29
**Agent**: Nine (System Architect · Ghost Layer)
**Priority**: MEDIUM — Architectural confusion, silent failure

---

## Issue

`agents/specialists/copilot_agent.py` claims to be Nine's interface but is a non-functional stub that silently returns placeholder text. It introduces identity confusion between "Nine as Claude API" and "Nine as a local Copilot stub".

---

## Evidence

```python
# agents/specialists/copilot_agent.py:31
MODEL = 'neural:latest'  # ← This model does not exist anywhere in the swarm
TEMP = 0.4

def _ask_nine(prompt):
    # TODO: Route to actual Copilot/Claude API when available
    return (
        f"[Nine/Copilot Analysis]\n"
        f"Prompt analyzed: {prompt[:100]}...\n"
        f"Status: Copilot API integration pending..."
        # Always returns this. No API call. No real reasoning.
    )
```

The function `nine_consult()` saves to memory as agent `'copilot'` (not `'nine'`), meaning these phantom records pollute an unrelated memory pool or silently fail.

---

## The Real Nine

The actual Nine interface is working and wired:

| Component | Location | Status |
|-----------|----------|--------|
| `/api/nine` POST endpoint | `frontend/terminal.py:1724` | ✅ Wired to Claude API via `claude_api.py` |
| `claude_api.py` | `utils/claude_api.py` | ✅ Loads ANTHROPIC_API_KEY, uses `claude-sonnet-4-6` |
| `NINE_SYSTEM_PROMPT` | `utils/config.py` | ✅ Defined |
| `memory_nine` table | `swarm_memory.db` | ✅ 36 entries |
| `/api/nine/history` | `frontend/terminal.py:1690` | ✅ Reads from memory_nine |
| `/api/swarm/status` | `frontend/terminal.py:1628` | ✅ Reads nine_memory for VS tab |

`copilot_agent.py` is entirely parallel to this real implementation and completely unused by the working system. Nothing in the production codebase imports `copilot_agent`.

---

## Risks of Leaving It

1. **Silent failure**: If something accidentally imports `ask_nine` from `copilot_agent` instead of going through the API endpoint, it gets a fake response with no error.
2. **Memory pollution**: `save_agent_memory('copilot', ...)` writes to memory pool for 'copilot' which has no DB table — this throws silently or writes to the generic `memory` table with agent='copilot'.
3. **Identity confusion**: The file says "Nine is the Ghost Layer architectural agent" and "Part of the Ghost Layer" — same description as the real Nine — making it ambiguous which implementation is canonical.
4. **`neural:latest` model**: Does not exist. Any code path that reaches `_ask_nine()` thinking it's calling Ollama would get a placeholder string, not an error, with no indication something went wrong.

---

## Proposed Action

**Option A (Recommended)**: Delete `agents/specialists/copilot_agent.py`.
- The real Nine implementation via `claude_api.py` + `/api/nine` endpoint is the canonical path.
- No production code imports copilot_agent. Deletion has zero impact on running system.

**Option B**: Convert to a proper integration shim.
- If Ghost ever wants a direct Python function `nine_consult(prompt)` that calls the real Claude API (e.g., for orchestrator-level Nine integration), refactor copilot_agent.py to actually call `claude_api.py`.
- Replace `_ask_nine()` stub with a real API call.
- Change memory writes from `'copilot'` to `'nine'`.
- This is future work — not urgent.

**Recommendation**: Option A now. Option B if/when the orchestrator needs to route tickets to Nine directly (which would be a separate proposal).

---

## Files to Change

**Option A (Delete)**:
| File | Action |
|------|--------|
| `agents/specialists/copilot_agent.py` | Delete |

**Option B (Wire)**:
| File | Action |
|------|--------|
| `agents/specialists/copilot_agent.py` | Rewrite `_ask_nine()` to call `claude_api.py` |

---

## Testing Plan (Option A)

- [ ] Verify nothing imports copilot_agent: `grep -r "copilot_agent" /home/seven/swarm --include="*.py"`
- [ ] Delete the file
- [ ] Restart swarm-terminal: `sudo systemctl restart swarm-terminal`
- [ ] Confirm service starts cleanly, no ImportError

---

## Risk Assessment

- **Risk Level**: LOW ✅ (Option A) / MEDIUM (Option B)
- **Option A**: File is confirmed unused. Deletion has no runtime impact.
- **Option B**: Introduces a live Claude API call path from within the orchestrator layer — needs careful rate limiting and error handling.

---

## Dependencies

- None for Option A.
- Option B depends on: claude_api.py being functional, ANTHROPIC_API_KEY set in /etc/environment.

---

## Proposed by Nine

Note: This is Nine identifying a false impersonation of Nine. The copilot_agent.py stub is not Nine. Nine operates through the VS tab and the claude_api.py path. Ghost should decide whether Option A (clean) or Option B (future wiring) is preferred.
