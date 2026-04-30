# SKILL: alm_create_proposal
# Test ALM Routing Fix — 2026-04-09

## Purpose
Test and verify the full ALM proposal lifecycle after the routing fix on 2026-04-09.

## Test Proposal
- **Title:** Test ALM routing fix
- **Scenario:** Verify full lifecycle: Chat/Studio raise → Pending → Approved → In Progress/sandbox → UAT auto → GIT wait → Prod approval → Done

## Steps to Validate
1. **Raise Proposal:**
   - Initiate a new proposal from Chat or Studio.
   - Confirm it enters the "Pending" state.
2. **Approval:**
   - Approve the proposal; it should move to "Approved".
3. **In Progress (Sandbox):**
   - Start work; status should become "In Progress" or "sandbox".
4. **UAT Auto-Promotion:**
   - On completion, proposal should auto-promote to UAT.
5. **GIT Wait:**
   - After UAT, status should be "GIT wait" (awaiting merge/deploy).
6. **Prod Approval:**
   - Approve for production; status should move to "Prod approval".
7. **Done:**
   - Finalize; status should become "Done".

## Expected Results
- Each status transition is enforced and auditable.
- No skipped or invalid transitions.
- UI and backend reflect correct state at each step.
- All environments (DEV/UAT/PROD) show correct status and allow only valid actions.

## Audit/Traceability
- Use this skill to validate the ALM routing logic after the 2026-04-09 fix.
- Document any issues or deviations for further refinement.

---
