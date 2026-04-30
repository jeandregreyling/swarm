# Decision 005: Establish Vortex Governance Boundary and Duck Review Path

**Status**: EXECUTED
**Decision ID**: 005
**Proposed**: 2026-03-30T01:19:00Z
**Executed**: 2026-03-30T01:19:08Z
**Agent**: Copilot (Ghost Layer)
**Work Proposal ID**: INTERNAL-TERMINAL_UI-0121
**Git Commit Hash**: [pending]

## Issue
The active governance model needed a clean Swarm-facing boundary before larger changes continue. The system also needed a consistent internal name for the time-state layer and a clear review path for proposals.

## Root Cause
Active docs and UI still referred to `Time Wizard`, while the intended operating model had evolved toward `Vortex`. The approval path using Duck and Sniffles existed conceptually, but was not yet documented as the active governance flow. The `.history` rollback layer also needed to be explicitly excluded from Fridays architecture.

## Proposed Solution
1. Treat `Vortex` as the active Swarm-facing name for the time-state layer.
2. Document that Swarm traceability ends at Vortex.
3. Explicitly mark `.history` as ghost-layer rollback only and outside Fridays architecture.
4. Document Duck as first review gate and Sniffles as escalation auditor.
5. Update active governance docs and active UI labels only, leaving historical records intact.

## Expected Outcome
- Swarm has a clean internal governance boundary.
- Proposal review path is understandable and consistent.
- Active UI and docs speak the same language.
- Historical documents remain historically accurate.

## Files Changed
- `docs/ALM_DRIVER.md`
- `docs/DEVELOPER_WORKFLOW.md`
- `docs/ARCHITECTURE.md`
- `docs/UAT_TEST_SCRIPTS.md`
- `docs/CHANGELOG.md`
- `frontend/templates/terminal_base.html`
- `frontend/templates/terminal_ui_v2.html`
- `frontend/theme_engine.py`
- `frontend/terminal.py`

## Test References
- `sandpits/twelve/logs/TEST-005-vortex-governance-boundary.md`

## Risk Assessment
- **Risk Level**: MEDIUM
- **Primary Risk**: Name transition may leave mixed legacy terminology in older records and internal implementation details.
- **Mitigation**: only update active operational surfaces; preserve historical docs as historical evidence.
- **Rollback**: restore active labels and governance wording while retaining proposal queue evidence.

## Execution Notes
- Internal ALM proposal created and executed through queue/work proposal lifecycle.
- Active governance docs now define Vortex boundary and Duck/Sniffles review path.
- Historical/archival records intentionally left unchanged.