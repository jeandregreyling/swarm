# Decision 001: Fix Duplicate /api/agents Route Definition

**Status**: PROPOSED  
**Decision ID**: 001  
**Proposed**: 2026-03-29T00:00:00Z  
**Agent**: Twelve (Time Wizard)  
**Git Commit Hash**: [PENDING]  

## Issue
The `frontend/terminal.py` file has TWO `@app.route('/api/agents')` definitions (lines 346 and 1367), causing Flask to throw:
```
AssertionError: View function mapping is overwriting an existing endpoint function: api_agents
```
This prevents the Fridays service from starting at all. Service startup fails immediately.

## Root Cause
During UI tile repair session (28 Mar 2026), first version of `/api/agents` endpoint was created at line 346 to return studio/roster data. Later, a second conflicting definition was added (or discovered) at line 1367 with different logic, causing the duplicate route conflict.

## Proposed Solution
1. **Audit both implementations** - Understand what each version returns
2. **Consolidate into ONE implementation** that serves both use cases OR create separate endpoints
3. **Test the unified endpoint** against Studio tile and Agent Roster tile
4. **Verify no other duplicate routes exist** in the file

Line 346 version returns: agent list with emoji metadata, model info  
Line 1367 version returns: agent roster data with enabled/temperature/status/ghost_layer flags

**Consolidated version should return** both formats OR clarify which is authoritative.

## Expected Outcome
- `/api/agents` returns clean JSON without conflicts
- Fridays service starts successfully on port 5050
- Both Studio tile and Agent Roster tile render correctly
- No Flask route conflicts

## Testing Plan
- [ ] Remove line 1367 duplicate, keep line 346
- [ ] Start Fridays service: `python3 frontend/terminal.py`
- [ ] Curl: `curl http://127.0.0.1:5050/api/agents | python3 -m json.tool`
- [ ] Verify JSON structure matches frontend expectations
- [ ] Test Studio tile loads agents with emoji
- [ ] Test Agent Roster tile displays agents with status

## Risk Assessment
- **Risk Level**: MEDIUM
- **Impact**: If wrong version is kept, UI tiles will blank again
- **Rollback**: Git revert to commit d54965e (previous working state)

## Code Changes
Files affected:
- `frontend/terminal.py` (line 346-365 AND 1367-1386): Duplicate route definition
- `frontend/templates/terminal_ui_v2.html` (implicitly depends on correct /api/agents format)

## Decision Chain Dependencies
- Blocks: Service startup (critical path)
- Related to: UI tile fixes from 28 Mar session
