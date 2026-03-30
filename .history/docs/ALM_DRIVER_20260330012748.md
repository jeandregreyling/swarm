# ALM Driver - Documentation-First Lifecycle

Date: 2026-03-30
Owner: Ghost Layer / Copilot
Scope: All mutating actions while Time Wizard is active

## Purpose

No undocumented changes are allowed. Documentation is the primary control plane, and implementation follows documented, approved proposals only.

## Policy (Effective Immediately)

1. Every mutating action must have a proposal record in `work_proposals`.
2. Every mutating API call must include `proposal_id`.
3. Proposal status must be `approved` or `executed` before write/execute actions run.
4. If a change is not documented, it is rejected.
5. Sniffles auditing remains enabled as continuous verification.

## Runtime Enforcement

Implemented in `frontend/terminal.py`:

- `POST /api/shell/execute` requires `proposal_id`
- `POST /api/skills/run` requires `proposal_id`
- `POST /api/exec` requires `proposal_id`
- `POST /api/exec/write` requires `proposal_id`

Gate behavior:

- Missing `proposal_id` => HTTP 428
- Unknown proposal => HTTP 404
- Proposal status not allowed => HTTP 403
- Allowed statuses => `approved`, `executed`

Configuration:

- `ALM_REQUIRE_APPROVALS=1` (default) enforces gate
- `ALM_REQUIRE_APPROVALS=0` disables gate for emergency debugging only

## Required Documentation Artifacts Per Change

1. Proposal record in queue/work proposals
2. Bug or task reference update
3. Changelog entry
4. Self-audit evidence (tests + endpoint checks)

## Audit Rule

Every execution cycle must produce:

- Dry-run result summary
- Connection check summary
- Proposal status summary
- Commit reference(s)

## Sniffles Requirement

Sniffles must remain enabled in agent roster and used for audit visibility.
Verification path: `GET /api/agents` includes `sniffles` with `enabled=true`.
