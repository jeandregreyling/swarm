# Developer Workflow: Using Agent Twelve's Time Wizard

**Effective Date**: 2026-03-29  
**Version**: 1.0  
**Audience**: All developers making changes to the swarm

---

## Overview

All code changes MUST be logged through the Time Wizard decision system. This ensures:
- ✅ Complete traceability (why was this change made?)
- ✅ Testability (was this tested before commit?)
- ✅ Reversibility (can we roll back if needed?)
- ✅ Visibility (can other agents understand the change?)
- ✅ Dependency tracking (what else depends on this?)

**Summary**: PROPOSE → TEST → LOG → EXECUTE → ARCHIVE → COMMIT

---

## The Time Wizard Workflow

### Step 1: PROPOSE — Create a Decision File

Create a new **decision proposal** in `sandpits/twelve/proposals/`:

**File naming**: `DECISION-NNN-slug.md` (e.g., `DECISION-003-fix-chat-sendMessage.md`)

**File location**: `/home/seven/swarm/sandpits/twelve/proposals/`

**Content template**: Use `sandpits/twelve/DECISION_TEMPLATE.md`

#### Example Decision File

```markdown
# Decision 003: Fix Chat sendMessage() Function

**Status**: PROPOSED  
**Decision ID**: 003  
**Proposed**: 2026-03-29T14:30:00Z  
**Agent**: Developer Name  
**Git Commit Hash**: [PENDING]  

## Issue
Chat interface displays but sendMessage() function is undefined.
Users cannot send messages. Error in browser console: "sendMessage is not defined"

## Root Cause
File `frontend/templates/terminal_ui_v2.html` has a dead #send-btn onclick handler
pointing to undefined function.

## Proposed Solution
1. Add sendMessage() function to terminal_ui_v2.html (lines ~1400)
2. Function reads #question-input, calls POST /api/chat
3. Append response to #chat-messages, clear input, scroll down
4. Add error handling for failed requests

## Expected Outcome
Users can type in chat input, click send, see messages appear in real-time.

## Testing Plan
- [ ] Unit test: sendMessage() is defined and callable
- [ ] Integration: sendMessage() correctly formats and sends request
- [ ] Manual: Try sending message in Fridays UI, verify it appears
- [ ] Regression: Verify no other chat functionality broke

## Risk Assessment
- **Risk Level**: LOW
- **Impact**: Only affects chat UI, no backend changes
- **Rollback**: Simple git revert

## Code Changes
Files affected:
- `frontend/templates/terminal_ui_v2.html` (add sendMessage function)
```

**Checklist before submitting**:
- [ ] Issue clearly described
- [ ] Root cause identified
- [ ] Solution is clear and scoped
- [ ] Testing plan exists
- [ ] Risk is assessed
- [ ] Files affected are listed

---

### Step 2: TEST — Document Tests & Run Them

Create test log in `sandpits/twelve/logs/`:

**File naming**: `TEST-NNN-slug.md` (e.g., `TEST-003-chat-sendMessage.md`)

**Run tests BEFORE making changes** to establish baseline, AFTER to verify.

#### Example Test Log

```markdown
# Test Log for DECISION-003

**Date**: 2026-03-29  
**Tester**: Claude Copilot  
**Decision**: DECISION-003 - Fix Chat sendMessage()  

## Test Environment
- Browser: Firefox latest
- Port: http://127.0.0.1:5050
- Service: Fridays terminal (swarm-terminal.service)

## Tests

### T1: Function Exists
Verify sendMessage() is defined in terminal_ui_v2.html
- [ ] Function found at line ~1400
- [ ] No syntax errors in function body
- [ ] onclick handler points to defined function

**Result**: ✅ PASS

### T2: API Call Format
Verify sendMessage() makes correct HTTP request
- [ ] Reads input from #question-input
- [ ] Posts to /api/chat
- [ ] Includes required headers (Content-Type: application/json)
- [ ] Includes conversation ID

**Result**: ✅ PASS

### T3: DOM Update
Verify response is correctly added to chat
- [ ] Message appears in #chat-messages
- [ ] Text is escaped (no XSS)
- [ ] Scroll position updates
- [ ] Input field is cleared

**Result**: ✅ PASS

### T4: Error Handling
Verify errors are handled gracefully
- [ ] Network error shows toast notification
- [ ] Error doesn't break UI
- [ ] User can retry

**Result**: ✅ PASS

### T5: Manual Fridays Test
Type message in Fridays UI and verify it sends
- [ ] Open http://127.0.0.1:5050
- [ ] Click Chat tile
- [ ] Type "Hello, Fridays"
- [ ] Click Send button
- [ ] Message appears in chat

**Result**: ✅ PASS

## Summary
All 5 tests passed. Ready for code commit.
```

---

### Step 3: LOG & UPDATE DECISION

Update the decision file with test results:

```markdown
## Test Results
- Test Log: sandpits/twelve/logs/TEST-003-chat-sendMessage.md
- All tests: PASS ✅
- Manual verification: PASS ✅
- Ready for execution

## Execution Notes
[To be filled during Step 4]
```

Also **update decision status** from `PROPOSED` to `TESTING` to `EXECUTED`.

---

### Step 4: EXECUTE — Make the Code Changes

Now that you've proposed and tested, implement the code:

```bash
# Make your changes
# Edit: frontend/templates/terminal_ui_v2.html
# Add sendMessage() function
```

After changes are complete:
1. **Verify tests still pass** with new code
2. **Update decision file** with execution notes
3. **Document any surprises** or deviations from plan

---

### Step 5: COMMIT — Record with Traceability

Use this commit message format:

```bash
git commit -m "DECISION-003: Fix chat sendMessage() function (TEST-003: PASS)

- Added sendMessage() function to terminal_ui_v2.html
- Connects #send-btn onclick to working handler
- Reads input, posts to /api/chat, updates DOM
- All 5 tests pass: unit + integration + manual
- No regressions detected

Decision ID: 003
Test Run: TEST-003
Status: EXECUTED
Traceability: sandpits/twelve/proposals/DECISION-003-*"
```

**Commit message structure**:
```
DECISION-NNN: [Title] (TEST-NNN: PASS)

[Bullet list of changes]

Decision ID: NNN
Test Run: TEST-NNN
Status: EXECUTED
Traceability: [Reference to decision files]
```

---

### Step 6: ARCHIVE — Record Completion

After successful commit, move decision to archive:

```bash
mv sandpits/twelve/proposals/DECISION-003-* sandpits/twelve/archive/
mv sandpits/twelve/logs/TEST-003-* sandpits/twelve/archive/
```

Create archive summary:

```
sandpits/twelve/archive/DECISION-003-chat-sendMessage/
├── DECISION-003-chat-sendMessage.md (original proposal + results)
├── TEST-003-chat-sendMessage.md (test results)
└── commit-abc1234567890.txt (commit hash for future reference)
```

---

## Time Wizard API Reference

Access decision history through these endpoints:

### GET /api/decisions
List all decisions (active + archived)

```bash
curl http://127.0.0.1:5050/api/decisions | python3 -m json.tool
```

**Response**:
```json
{
  "decisions": [
    {
      "id": "001",
      "title": "Fix Duplicate /api/agents Route Definition",
      "status": "EXECUTED",
      "proposed": "2026-03-29",
      "category": "Backend/API",
      "impact": "CRITICAL"
    }
  ],
  "total": 1
}
```

### GET /api/timeline
Chronological timeline of all decisions

```bash
curl http://127.0.0.1:5050/api/timeline | python3 -m json.tool
```

**Response**:
```json
{
  "timeline": [
    {
      "decision_id": "001",
      "file": "DECISION-001-fix-duplicate-api-agents.md",
      "status": "EXECUTED",
      "proposed": "2026-03-29T00:00:00Z",
      "title": "001: Fix Duplicate /api/agents"
    }
  ],
  "total": 1
}
```

### GET /api/decisions/<id>
Get full details of a specific decision

```bash
curl http://127.0.0.1:5050/api/decisions/001 | python3 -m json.tool
```

---

## Decision Index

Update `sandpits/twelve/DECISION_INDEX.md` when you create new decisions:

```markdown
| 003 | Fix Chat sendMessage() Function | PROPOSED | 2026-03-29 | Frontend/UI | MEDIUM |
```

This maintains the living index of all swarm decisions.

---

## Checklist Before Committing

- [ ] Decision proposal written (DECISION-NNN.md)
- [ ] Tests documented (TEST-NNN.md)
- [ ] Tests run and passed
- [ ] Code changes made
- [ ] Code tests verified
- [ ] Decision file updated with results
- [ ] Commit message references DECISION ID
- [ ] Commit message references TEST ID
- [ ] No merge conflicts
- [ ] No breaking changes to other systems

---

## Examples

### Bad Workflow (❌ DO NOT DO THIS)
```
1. Edit code
2. git commit -m "Fix chat"  ← No decision reference
3. Push
4. Ask "Did this break anything?"
```

### Good Workflow (✅ DO THIS)
```
1. Create DECISION-003 proposal
2. Create TEST-003 test plan
3. Run tests manually first
4. Edit code
5. Verify tests pass again
6. Update decision with results
7. git commit -m "DECISION-003: Fix chat..."  ← With ID reference
8. Push
9. Archive decision
```

---

## Questions?

When in doubt:
1. Read the decision template (`DECISION_TEMPLATE.md`)
2. Review existing decisions (e.g., DECISION-001)
3. Check this document's examples
4. Ask in #development or escalate to Ghost Layer

---

## Historical Record

**Workflow Version**: 1.0  
**Created**: 2026-03-29 (DECISION-002)  
**Last Updated**: 2026-03-29  
**Effective**: All changes from 2026-03-29 onward
