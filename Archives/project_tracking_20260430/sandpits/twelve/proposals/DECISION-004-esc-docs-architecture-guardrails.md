# Decision 004: Bake ESC Invariant + Docs Reading Home + Terminal/Theme Sync Guardrails

**Status**: EXECUTED
**Decision ID**: 004
**Proposed**: 2026-03-30T00:40:00Z
**Executed**: 2026-03-30T00:43:00Z
**Agent**: Copilot (Ghost Layer)
**Work Proposal ID**: INTERNAL-TERMINAL_UI-0120
**Git Commit Hash**: [pending]

## Issue
The platform needed architecture-level enforcement for:
1. Deterministic ESC close behavior.
2. Strict synchronization between terminal API behavior and theme/template rendering.
3. A more operational Docs home (search, right-side section controls, metadata visibility, and ALM traceability).

## Root Cause
UI behavior and policy were partially implemented across layers but not fully locked as explicit architecture rules with complete proposal lifecycle evidence.

## Proposed Solution
1. Harden ESC handling in the UI runtime with clear stack priority and capture-phase handling.
2. Redesign Docs library view into a searchable catalogue with a right-side section panel, quick governance links, and selected-doc metadata.
3. Expand docs API metadata (`kind`, `section`, `modified_at`) for richer client rendering.
4. Record policy and guardrail requirements in ALM and developer workflow documentation.
5. Create and execute a formal internal proposal through ALM lifecycle APIs.

## Expected Outcome
- ESC behavior is deterministic and architecture-documented.
- Docs tile acts as a reading control center instead of a flat list.
- Terminal/backend docs metadata supports richer UX.
- Policy remains traceable in ALM docs, workflow docs, and executed proposal records.

## Files Changed
- `frontend/templates/terminal_base.html`
- `frontend/terminal.py`
- `docs/ALM_DRIVER.md`
- `docs/DEVELOPER_WORKFLOW.md`
- `docs/CHANGELOG.md`

## Test References
- `sandpits/twelve/logs/TEST-004-esc-docs-architecture-guardrails.md`

## Risk Assessment
- **Risk Level**: MEDIUM
- **Primary Risk**: ESC event ordering can regress if new components add independent key handlers.
- **Mitigation**: Capture-phase ESC handling + documented invariant + UAT checks.
- **Rollback**: Revert frontend ESC and docs-render blocks while retaining docs policy artifacts.

## Execution Notes
- Internal ALM proposal created via `POST /api/queue`.
- Proposal status moved to `approved` then `executed` via `PATCH /api/work-proposals/<proposal_id>`.
- API verification captured for ALM status and docs list availability.
