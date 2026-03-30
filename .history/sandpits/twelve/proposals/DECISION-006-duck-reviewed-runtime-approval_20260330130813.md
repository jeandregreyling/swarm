# Decision 006: Enforce Duck-Reviewed Proposal Approvals at Runtime

**Status**: EXECUTED
**Decision ID**: 006
**Proposed**: 2026-03-30T02:06:39Z
**Executed**: 2026-03-30T02:07:10Z
**Agent**: Copilot (Ghost Layer)
**Work Proposal ID**: INTERNAL-TERMINAL_UI-0132
**Git Commit Hash**: [pending]

## Issue
The Duck-first review path for Vortex governance existed in active documentation, but the runtime work-proposal API still allowed approvals without a Duck review and allowed execution to skip the approved state.

## Root Cause
`/api/work-proposals/<proposal_id>` updated proposal status directly without validating transition order or invoking any review logic. That left the governance flow documented but not enforced.

## Proposed Solution
1. Add a Duck review helper to the runtime proposal API.
2. Require `pending -> approved` to pass Duck review.
3. Log Duck proposal review evidence in `duck_log` and lifecycle evidence in `activity_log`.
4. Restrict `executed` to proposals that are already `approved`.
5. Update active ALM docs and UAT coverage to reflect the enforced runtime path.

## Expected Outcome
- Weak proposals are blocked before approval.
- Queue-visible proposal reviews are auditable through the existing Duck evidence path.
- Runtime behavior matches the documented `PROPOSE -> REVIEW -> APPROVE -> EXECUTE` flow.

## Files Changed
- `frontend/terminal.py`
- `docs/ALM_DRIVER.md`
- `docs/UAT_TEST_SCRIPTS.md`
- `docs/CHANGELOG.md`

## Test References
- `sandpits/twelve/logs/TEST-006-duck-reviewed-runtime-approval.md`

## Risk Assessment
- **Risk Level**: MEDIUM
- **Primary Risk**: existing manual workflows may expect direct `pending -> executed` transitions.
- **Mitigation**: enforcement is limited to the proposal status API and returns explicit transition errors.
- **Rollback**: remove the review helper and transition guard while retaining the recorded governance evidence.

## Execution Notes
- Duck review now runs at proposal approval time rather than only in documentation.
- Weak proposal validation was confirmed live on a patched server instance.
- The runtime bake proposal itself was logged and executed through `INTERNAL-TERMINAL_UI-0132`.

*** Add File: /home/seven/swarm/sandpits/twelve/logs/TEST-006-duck-reviewed-runtime-approval.md
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