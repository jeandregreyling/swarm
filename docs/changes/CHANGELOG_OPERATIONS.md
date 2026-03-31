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
- Time (UTC): 2026-03-31T01:15:47Z
- Actor: copilot
- Scope: docs/registry/FILE_REGISTRY.md, docs/FRIDAYS_BUG_FIX_LOG.md, docs/FILE_STRUCTURE.md, docs/registry/FILING_SYSTEM.md, ALM-gated workflow documentation
- Change: Cleared VS Code markdown problems backlog by fixing table delimiter style, heading semantics, fenced-code language tags, and filing-rule placeholder escaping; updated Fridays fix log to reflect trust/ALM hardening outcomes.
- Validation: VS Code Problems scan reduced from 117 markdown findings to clean state; formatting and docs consistency checks passed in editor diagnostics.
- Rollback: Revert touched documentation files and re-run diagnostics.
- Time (UTC): 2026-03-30T07:20:00Z
- Actor: copilot
- Scope: core/time_machine.py, frontend/terminal.py, frontend/theme_engine.py
- Change: Hardened Vortex dry-run for legacy checkpoint schema, pinned TimeMachine imports to core in runtime and theme layers, reduced checkpoint list payload size.
- Validation: dry-run matrix OK 20/0, live API dry_run on system_bootstrap returned ok=true, ALM status endpoint healthy.
- Rollback: Revert touched files and restart terminal service.
- Time (UTC): 2026-03-30T07:15:38Z
- Actor: copilot
- Scope: docs filing
- Change: Established canonical filing system and linked core docs
- Validation: Created registry/changes/audits/runbook files and updated references in structure/workflow/tracker docs
- Rollback: Revert added docs and remove references if needed


---
## 2026-03-30 — E2E Test Suite + Ticket PATCH Bug Fix
- Date: 2026-03-30
- Author: Nine (AI) / session
- Scope: tests/test_e2e_fridays.py + frontend/terminal.py
- Changes:
  1. CREATED tests/test_e2e_fridays.py — 21-test executable e2e suite (REQ-001 to REQ-020)
     Pure urllib, no external deps, exit-code = failure count
  2. FIXED frontend/terminal.py api_ticket_patch() — tickets.priority does not exist;
     priority lives in queue table. Rewrote to two separate UPDATEs:
       UPDATE tickets SET tags=? WHERE ticket_number=?
       UPDATE queue SET priority=? WHERE id=(SELECT queue_id FROM tickets WHERE ticket_number=?)
  3. FIXED test REQ-002 — chat client timeout raised 5s→15s to allow server's 10s fallback
  4. FIXED test REQ-006 — assertion updated from 'entries' key to 'queue' key
  5. FIXED test REQ-012 — checkpoint field changed to 'checkpoint_name'; dry-run POST body key fixed
  6. FIXED test REQ-020 — queue create returns 201 (not 200); read-back now checks nested queue.id
- Validation: python3 tests/test_e2e_fridays.py → 21 PASS  0 FAIL  0 ERROR
- Rollback: Revert api_ticket_patch() to single UPDATE; restore test assertions
- Time (UTC): 2026-03-31T01:27:17Z
- Actor: copilot
- Scope: ghost-layer/ten
- Change: Remap Ten from Gemini to Copilot
- Validation: Updated terminal roster + DB agents model to gpt-5.3-codex; created sandpits/ten workspace and registered it in FILE_REGISTRY.
- Rollback: Revert frontend/terminal.py, utils/config.py, docs/registry/FILE_REGISTRY.md; set agents.ten model back to gemini-1.5-pro if needed.

- Time (UTC): 2026-03-31T01:29:32Z
- Actor: copilot
- Scope: fridays/agent-roster-doc-sync
- Change: Sync Ten Copilot labels in Fridays UI/docs
- Validation: Updated Ten role label in frontend roster API and refreshed active AGENT_TWELVE_STATUS architecture block to show Copilot mapping + ten sandpit.
- Rollback: Revert frontend/terminal.py and docs/AGENT_TWELVE_STATUS.md if rollback required.

- Time (UTC): 2026-03-31T01:38:49Z
- Actor: copilot
- Scope: fridays/chat-agent-routing
- Change: Add selectable agent chat in shared thread
- Validation: Updated /api/chat to route by selected agent with shared conversation_id and prior-thread context; added chat agent selector in terminal templates.
- Rollback: Revert frontend/terminal.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

