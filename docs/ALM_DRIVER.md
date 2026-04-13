# ALM Driver - Documentation-First Lifecycle

Date: 2026-03-30
Owner: Ghost Layer / Ten (GPT)
Scope: All mutating actions while Vortex is active

## Purpose

No undocumented changes are allowed. Documentation is the primary control plane, and implementation follows documented, approved proposals only.

Vortex is the Swarm-facing time-state layer. It is the end of the internal traceability path.

Boundary rule:

- `.history` is not part of Fridays or Swarm governance.
- `.history` remains ghost-layer rollback infrastructure only.
- Swarm documentation, UI, and approvals stop at Vortex.

## Policy (Effective Immediately)

1. Every mutating action must have a proposal record in `work_proposals`.
2. Every mutating API call must include `proposal_id`.
3. Proposal status must be `approved` or `executed` before write/execute actions run.
4. If a change is not documented, it is rejected.
5. Duck is the first logic gate for proposal review.
6. Sniffles remains the escalation auditor when Duck flags uncertainty or risk.
7. Sniffles auditing remains enabled as continuous verification.

## Change Classes

Use the lightest viable governance class that preserves traceability.

- `TRIVIAL`: formatting, typo, comments, non-behavioral polish.
- `FEATURE`: new or changed user/API capability.
- `ARCHITECTURE`: runtime invariants, system boundaries, data shape changes.
- `GOVERNANCE`: workflow, approval, traceability, or audit-policy changes.

All non-trivial changes still require proposal queue visibility.

## Runtime Enforcement

Implemented in `frontend/terminal.py`:

- `POST /api/shell/execute` requires `proposal_id`
- `POST /api/skills/run` requires `proposal_id`
- `POST /api/exec` requires `proposal_id`
- `POST /api/exec/write` requires `proposal_id`
- `POST /api/agents/capabilities` requires Ghost identity (effective user `ghost`)

Visibility endpoints:

- `GET /api/alm/status` exposes governance state for Fridays UI and audits.
- `GET /api/agents/capability-matrix` exposes granted capabilities and trust levels by agent.

Gate behavior:

- Missing `proposal_id` => HTTP 428
- Unknown proposal => HTTP 404
- Proposal status not allowed => HTTP 403
- Allowed statuses => `approved`, `executed`

Configuration:

- `ALM_REQUIRE_APPROVALS=1` (default) enforces gate
- `ALM_REQUIRE_APPROVALS=0` disables gate for emergency debugging only

## Capability Governance (High-Access Toggle)

Fridays Skills now includes an Agent Capability Matrix with operational controls:

- filter presets (`Git Executors`, `High Trust (2+)`, `No Git Access`)
- one-click high-access bundle enable/disable per agent
- per-agent quick toggle for `git_execute`

Runtime policy:

1. Capability mutation is Ghost-only at API layer.
2. UI blocks capability mutation unless effective identity is `ghost`.
3. Every capability mutation is logged in activity for audit trace.

High-access bundle used by the UI:

- `git_propose`
- `git_execute`
- `propose_work`
- `coordinate`
- `shared_write`
- `memory_read_all`
- `skill_shell`
- `skill_schedule`

Mutation endpoint contract:

- `POST /api/agents/capabilities`
  - input: `agent`, `capability` or `capabilities`, `enabled`, identity payload
  - success: returns updated granted capability rows for target agent
  - auth failure: HTTP `403`
  - unknown capability: HTTP `400`
  - unknown agent: HTTP `404`

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

## Duck + Sniffles Review Path

Full 6-stage automated lifecycle (as of 2026-04-13):

```text
pending → approved → in_progress → done → uat → executed
```

1. **Proposal submitted** — enters `work_proposals` with status `pending`.
2. **Duck review** (`duck_review_proposal()`) — sanity-checks title/description. Posts result to originating chat thread.
   - Approved: agent receives `SKILL alm_self_approve <id>` + `SKILL alm_complete <id>` instructions.
   - Rejected: agent receives revision guidance. Status → `rejected`.
3. **Agent builds** — agent runs `SKILL alm_self_approve <id>` → status `in_progress`. Makes changes, then runs `SKILL alm_complete <id>` → status `done`.
4. **Duck QA check** (`duck_check_done()`) — auto-triggered on `done`. Runs quality gate.
   - Pass: status → `uat`. Chat notified: "Ghost, review in UAT tab."
   - Fail: status → `in_progress`. Agent receives feedback, must fix and re-complete.
5. **UAT** — Ghost reviews the work in Studio → UAT tab. Options:
   - Mark Executed manually → status `executed`.
   - "Ask Duck to Execute" → calls `duck_execute_proposal()` → status `executed`, chat notified.
   - Reopen → status `in_progress` for further work.
6. **Executed** — shipped to production. Proposal closed.

If Sniffles flags ambiguity or risk at any stage, it escalates for deeper audit.

Current state:

- Proposal queue visibility and ALM execution gate are implemented.
- `PATCH /api/work-proposals/<proposal_id>` triggers `notify_proposal_status_change()` for all status transitions, posting actionable messages to the originating chat thread.
- `POST /api/work-proposals/<proposal_id>/duck-execute` — Ghost tells Duck to ship a UAT proposal.
- `uat` is a required intermediate stage between `done` and `executed` — Duck quality check must pass first.
- Duck/Sniffles are the documented review authorities for this workflow.

## Sniffles Requirement

Sniffles must remain enabled in agent roster and used for audit visibility.
Verification path: `GET /api/agents` includes `sniffles` with `enabled=true`.

## Fridays Visibility (Baked In)

The UI must visibly show governance state so policy is observable, not implicit.

- Home dashboard stat card: `ALM` (`ON` or `WARN`)
- Studio header governance line: ALM status + Sniffles + pending queue count
- Monitor panel governance block: enforcement badge + queue counters

Data source for all UI indicators: `GET /api/alm/status`

## Proposal Detail Workflow Surface (Studio)

Past proposals in Studio history open a detail modal that now includes:

- Workflow lifecycle: Proposed -> Reviewed -> Executed -> Archived
- Rationale context: title + description shown as the "why"
- Ownership context: proposing agent shown as the "who"
- Documentation links: ALM Driver + Change Log
- Test links (when applicable by content keywords):
  - `docs/testing/ALM_TEST_SPECIFICATION.md`
  - `docs/testing/TIME_WIZARD_TESTS.md`
  - `docs/UAT_TEST_SCRIPTS.md`

This gives a single click path from proposal history to evidence and test artifacts.

### Studio Button Legend (What each button does)

In Studio, proposal cards and proposal detail modals expose the following controls:

- `✓ Approve` (pending only)
  - Action: sets proposal status to `approved`.
  - API: `PATCH /api/work-proposals/<proposal_id>` with `{ "status": "approved" }`.
  - Effect: proposal becomes eligible for ALM-gated execution.

- `✗ Reject` (pending only)
  - Action: sets proposal status to `rejected`.
  - API: `PATCH /api/work-proposals/<proposal_id>` with `{ "status": "rejected" }`.
  - Effect: proposal is blocked from ALM-gated execution.

- `ALM Test Specification`
  - Action: opens ALM test specification document in the doc detail modal.
  - Purpose: verification checklist and requirement mapping.

- `Vortex Test Suite`
  - Action: opens the Vortex test suite document in the doc detail modal.
  - Purpose: validates session/timeline/checkpoint behavior.

- `UAT Test Scripts`
  - Action: opens UAT script document in the doc detail modal.
  - Purpose: manual acceptance cycle for end-to-end checks.

- `ALM Driver`
  - Action: opens this governance policy document.
  - Purpose: defines ALM enforcement and traceability rules.

- `Change Log`
  - Action: opens change history.
  - Purpose: who changed what and when.

Note:

- Approve/Reject buttons only render for `pending` proposals.
- History proposals (`approved`, `executed`, `rejected`) show workflow and evidence links; they are no longer actionable.

## ALM Test Cycle (Who / Why / What)

1. Propose (Who: agent)

- Why: capture intended change and expected impact before execution.
- What: `work_proposals` row with title/description/proposal_id.

1. Review (Who: Duck first, Sniffles if needed, Ghost for final control)

- Why: prevent unapproved or weakly-reasoned mutating actions.
- What: queue-visible logic pass, escalation audit when flagged, then approve/reject.

1. Execute (Who: runtime endpoints under ALM gate)

- Why: only approved or executed proposals may run writes/exec/shell/skills.
- What: gate enforces `proposal_id` and status checks (428/404/403 on failure).

1. Verify (Who: operator + tests)

- Why: ensure behavior and safety after change.
- What: endpoint checks, dry tests, targeted suites in `docs/testing`.

1. Document (Who: implementing agent)

- Why: maintain traceability and auditability.
- What: update changelog, state snapshot/self-audit, and task tracker evidence.

## Theme Sync Rule (Mandatory)

Every governance/UI/API visibility change must be applied in both layers:

1. Console/API layer (`frontend/terminal.py`)
2. Theme/render layer (`frontend/theme_engine.py` and relevant templates)

A terminal startup reminder is now present in `frontend/terminal.py` to enforce this behavior during implementation.

## ESC Close Invariant (Architecture Rule)

ESC behavior is now a hard UI invariant across all interactive surfaces.

Priority order for ESC actions:

1. Close the top-most open modal/overlay.
2. If no modal is open, close the top-most visible window.
3. If no window is open, close command palette/help overlays.
4. Never close multiple layers in one key press.

Implementation notes:

- ESC listener runs in capture phase to avoid inner component conflicts.
- Handler explicitly stops propagation after a successful close action.
- Close order must remain stack-safe and deterministic.

Validation requirement:

- Any new modal/window feature must include an ESC close-path check in manual UAT.

## Docs Reading Home Rule

The Docs tile is an operational console, not a static list.

Required baseline capabilities:

- Search-first document catalogue.
- Right-side section navigator.
- Quick links for governance/test docs.
- Last-changed metadata visibility for selected docs.
- ALM history tab remains visible from the same panel.

Any changes to docs discovery, metadata shape, or rendering must update both:

1. `frontend/terminal.py` docs APIs
2. `frontend/templates/terminal_base.html` docs rendering logic
