# SKILL: alm_create_proposal
# Final routing test — 2026-04-09

## Purpose
Test the full ALM proposal lifecycle after the final orchestrator.py patch.

## Test Proposal
- **Title:** Final routing test
- **Scenario:** Should now appear in Pending, move to In Progress on approval, auto-apply to UAT

## Steps to Validate
1. **Raise Proposal:**
   - Initiate a new proposal; confirm it enters the "Pending" state.
2. **Approval:**
   - Approve the proposal; it should move to "In Progress" and auto-apply to UAT.
3. **UAT Auto-Promotion:**
   - Confirm UAT auto-apply is triggered and status is updated.

## Expected Results
- Each status transition is enforced and auditable.
- Proposal appears in Pending, then In Progress, and triggers UAT auto-apply.
- All environments reflect correct state.

---
