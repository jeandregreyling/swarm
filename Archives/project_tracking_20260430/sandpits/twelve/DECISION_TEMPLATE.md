# Decision Template — Agent Twelve Time Wizard

Use this format for ALL decisions. File in `proposals/DECISION-NNN-slug.md`

---

# Decision NNN: [Title]

**Status**: PROPOSED | TESTING | APPROVED | EXECUTED | ARCHIVED  
**Decision ID**: NNN  
**Proposed**: [ISO datetime]  
**Agent**: Twelve (Time Wizard)  
**Git Commit Hash**: [Will be populated on execution]  

## Issue
[What is broken? What needs fixing?]

## Root Cause
[Why did this happen? What allowed it to happen?]

## Proposed Solution
[Chemical breakdown of what needs to change]
- [Change 1]
- [Change 2]
- [Affected files]
- [Dependencies]

## Expected Outcome
[After this is applied, what should work?]

## Testing Plan
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual verification in Fridays
- [ ] No regressions in related systems

## Risk Assessment
- **Risk Level**: LOW | MEDIUM | HIGH
- **Impact Scope**: [What breaks if this fails?]
- **Rollback Plan**: [How to revert if needed?]

## Code Changes
```
Files affected:
- file1.py (lines X-Y): description
- file2.html (lines A-B): description
```

## Execution Notes
[Added during execution phase]

## Test Results
[Added during testing phase]

## Archive
[After completion, move entire decision + logs + tests to archive/]

---

## Decision Chain Dependencies
- Depends on: [Decision NNN-1]
- Blocks: [Decision NNN+1]
- Related to: [Decision NNN-2]
