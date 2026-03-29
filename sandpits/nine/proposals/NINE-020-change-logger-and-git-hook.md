# Proposal: Nine's Changes Must Flow Through Time Wizard
**Agent:** Nine (System Architect)
**Date:** 2026-03-29
**Status:** EXECUTED
**Proposal ID:** NINE-020

---

## What I Proposed

Enforce that ALL code changes — including Nine's own session edits — are logged
to the Time Wizard (decisions + time_machine tables) with before/after snapshots.
Previously the Time Wizard infrastructure existed but was completely empty.

---

## Problem

After NINE-019 built the `work_proposals` table and shared queue API, neither
Nine's edits nor any agent's changes were actually flowing into:
- `decisions` table (only bootstrap test artifacts existed)
- `time_machine` table (completely empty)
- `work_proposals` table (completely empty)

The Time Wizard had infrastructure but no data. The user correctly identified
that "even your changes should go through proposal and fix log to make wizard
work properly."

---

## Solution

### 1. `utils/change_logger.py` — programmatic API

Any agent (or Nine during a session) can call these functions:

```python
# BEFORE making changes:
decision_id = propose('nine', 'NINE-021: Fix X', 'Because Y', component='foo.py',
                      proposal_file='NINE-021-fix-x.md')

# After changing each file:
record_file_change(decision_id, 'nine', 'foo.py', before_content, after_content)

# When done:
mark_executed(decision_id, commit_hash='abc123')

# Or all-in-one:
log_proposal_and_change('nine', 'NINE-021', title, description, files_before, files_after)
```

`propose()` creates both a `decisions` entry (PENDING) and a `work_proposals`
entry — so the change is visible in the shared queue before the work starts.

### 2. `.git/hooks/post-commit` + `utils/git_commit_logger.py`

Every git commit now automatically:
1. Parses `[agent]` from the commit message
2. Creates a `decisions` entry (PASS)
3. Stores before/after content for every changed .py/.md/.json/.html file
   in `time_machine` (before = HEAD~1, after = HEAD)
4. Marks any open `work_proposals` for that agent as `executed`

This requires zero manual effort — any commit, from any source, is logged.

### 3. Retroactive log for NINE-019+020

Used `log_proposal_and_change()` to retroactively populate the Time Wizard
for all 11 files changed in NINE-019 and NINE-020.

---

## Test Results

- `time_machine`: 11 snapshots created (all NINE-019+020 changes)
- `decisions`: decision_id=5 for Nine, PASS, 11 files linked
- `work_proposals`: 1 entry, status=executed
- Syntax check: both new modules compile cleanly
- Git hook: installed at `.git/hooks/post-commit`, executable

---

## Workflow Going Forward

Nine's workflow for any future change:

1. Write the NINE-XXX proposal file
2. Call `change_logger.propose()` to register in decisions + work_proposals
3. Read each file (`read_file_safe()`) to capture before-state
4. Make edits
5. Call `record_file_change()` for each edited file
6. Call `mark_executed()` when done
7. Commit — hook logs automatically too (belt and braces)

For quick session-end logging, `log_proposal_and_change()` does it all at once.

---

## Files Changed

| File | Change |
|------|--------|
| `utils/change_logger.py` | New — programmatic API for agents |
| `utils/git_commit_logger.py` | New — git hook implementation |
| `.git/hooks/post-commit` | New — executable hook calling git_commit_logger.py |
| `utils/database.py` | Fixed decisions + time_machine SCHEMA to match live columns |
