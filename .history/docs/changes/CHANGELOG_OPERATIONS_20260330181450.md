# Operations Change Log (Canonical)

This is the canonical append-only change ledger for operational and code changes.

## Entry Template
- Time (UTC):
- Actor:
- Scope:
- Change:
- Validation:
- Rollback:

---

## Entries
- Time (UTC): 2026-03-30T07:20:00Z
- Actor: copilot
- Scope: core/time_machine.py, frontend/terminal.py, frontend/theme_engine.py
- Change: Hardened Vortex dry-run for legacy checkpoint schema, pinned TimeMachine imports to core in runtime and theme layers, reduced checkpoint list payload size.
- Validation: dry-run matrix OK 20/0, live API dry_run on system_bootstrap returned ok=true, ALM status endpoint healthy.
- Rollback: Revert touched files and restart terminal service.
