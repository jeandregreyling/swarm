# Test Log for DECISION-006

**Test ID**: TEST-006
**Decision**: DECISION-006 - Duck-Reviewed Runtime Approval
**Date**: 2026-03-30
**Tester**: Copilot (Ghost Layer)
**Linked Work Proposal**: INTERNAL-TERMINAL_UI-0132

## Scope
Validate the runtime Duck review gate for work-proposal approvals and confirm execution cannot skip the approved state.

## Tests

### T1: Static Validation
- Method: editor diagnostics on the patched API file
- Check:
  - `frontend/terminal.py`
- Result: PASS

### T2: Weak Proposal Blocked
- Server: patched runtime instance on `http://127.0.0.1:5051`
- Proposal: `INTERNAL-TERMINAL_UI-0129`
- Action: `PATCH /api/work-proposals/INTERNAL-TERMINAL_UI-0129` with `{"status":"approved"}`
- Expected:
  - HTTP `403`
  - `error: duck review blocked approval`
  - `duck_review.result: NO`
- Result: PASS

### T3: Strong Proposal Approved
- Server: patched runtime instance on `http://127.0.0.1:5051`
- Proposal: `INTERNAL-TERMINAL_UI-0130`
- Action: `PATCH /api/work-proposals/INTERNAL-TERMINAL_UI-0130` with `{"status":"approved"}`
- Expected:
  - HTTP `200`
  - `duck_review.result: YES`
  - proposal status becomes `approved`
- Result: PASS

### T4: Approved Proposal Executed
- Server: patched runtime instance on `http://127.0.0.1:5051`
- Proposal: `INTERNAL-TERMINAL_UI-0130`
- Action: `PATCH /api/work-proposals/INTERNAL-TERMINAL_UI-0130` with `{"status":"executed"}`
- Expected:
  - HTTP `200`
  - proposal status becomes `executed`
- Result: PASS

### T5: Pending Execute Blocked
- Server: patched runtime instance on `http://127.0.0.1:5051`
- Proposal: `INTERNAL-TERMINAL_UI-0131`
- Action: `PATCH /api/work-proposals/INTERNAL-TERMINAL_UI-0131` with `{"status":"executed"}`
- Expected:
  - HTTP `403`
  - error includes `invalid transition: pending -> executed`
- Result: PASS

### T6: Implementation Proposal Lifecycle
- Server: patched runtime instance on `http://127.0.0.1:5051`
- Proposal: `INTERNAL-TERMINAL_UI-0132`
- Actions:
  1. `POST /api/queue`
  2. `PATCH /api/work-proposals/INTERNAL-TERMINAL_UI-0132` -> `approved`
  3. `PATCH /api/work-proposals/INTERNAL-TERMINAL_UI-0132` -> `executed`
- Result: PASS

## Summary
- Duck-first proposal review is now enforced at runtime.
- Proposal execution can no longer skip the approved state through the status API.
- Runtime behavior now matches the active Vortex governance model.