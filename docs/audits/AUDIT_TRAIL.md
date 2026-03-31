# Audit Trail (Canonical, Append-Only)

This file is the canonical audit evidence trail for Swarm changes.
Do not rewrite history entries. Append only.

## Entry Template
- Audit ID:
- Time (UTC):
- Actor:
- Objective:
- Evidence:
- Result:
- Follow-up:

---

## Entries
- Audit ID: AUDIT-20260331-docs-alm-fridays-cleanup
- Time (UTC): 2026-03-31T01:15:47Z
- Actor: copilot
- Objective: Close VS Code documentation diagnostics and align Fridays/ALM records with implemented trust and governance controls.
- Evidence: Updated markdown delimiters and fenced blocks, corrected heading semantics, escaped naming placeholders in filing standard, and recorded remediation in canonical ledgers.
- Result: PASS
- Follow-up: Keep change+audit entries appended via ops/scripts/log_change.sh for each future doc and policy update.
- Audit ID: AUDIT-20260330-vortex-dryrun-stability
- Time (UTC): 2026-03-30T07:21:00Z
- Actor: copilot
- Objective: Eliminate Vortex dry-run failures and ensure ALM-visible persistence.
- Evidence: system_bootstrap dry-run succeeded via API, activity_log service=vortex entries present, theme and runtime import pinning applied.
- Result: PASS
- Follow-up: Add automated audit endpoint for checkpoint->dry-run->log bundle.
- Audit ID: AUDIT-20260330-071538
- Time (UTC): 2026-03-30T07:15:38Z
- Actor: copilot
- Objective: Established canonical filing system and linked core docs
- Evidence: Created registry/changes/audits/runbook files and updated references in structure/workflow/tracker docs
- Result: PASS
- Follow-up: Revert added docs and remove references if needed


---
## 2026-03-30 — Post-Fix E2E Audit
- Date: 2026-03-30
- Scope: Fridays / Swarm terminal API (21 requirements)
- Auditor: Nine (AI) / automated test suite
- Baseline: 16 PASS  5 FAIL  0 ERROR (pre-fix run)
- Failures identified:
  REQ-002 REAL BUG — chat endpoint blocked indefinitely (no timeout) [FIXED: 10s ThreadPoolExecutor]
  REQ-006 TEST BUG — queue key was 'entries', is 'queue' [FIXED: assertion updated]
  REQ-012 TEST BUG — checkpoint field/dry-run body key wrong [FIXED: checkpoint_name used]
  REQ-018 REAL BUG — api_ticket_patch tried UPDATE tickets SET priority=? (priority not in tickets) [FIXED: split UPDATEs]
  REQ-020 TEST BUG — queue create returns 201, test expected 200; nested read-back [FIXED]
- Post-fix result: 21 PASS  0 FAIL  0 ERROR
- March 28 audit REQ-002 blocker (chat timeout): RESOLVED
- Status: PASS — ready for UAT
- Audit ID: AUDIT-20260331-012717
- Time (UTC): 2026-03-31T01:27:17Z
- Actor: copilot
- Objective: Remap Ten from Gemini to Copilot
- Evidence: Updated terminal roster + DB agents model to gpt-5.3-codex; created sandpits/ten workspace and registered it in FILE_REGISTRY.
- Result: PASS
- Follow-up: Revert frontend/terminal.py, utils/config.py, docs/registry/FILE_REGISTRY.md; set agents.ten model back to gemini-1.5-pro if needed.

- Audit ID: AUDIT-20260331-012932
- Time (UTC): 2026-03-31T01:29:32Z
- Actor: copilot
- Objective: Sync Ten Copilot labels in Fridays UI/docs
- Evidence: Updated Ten role label in frontend roster API and refreshed active AGENT_TWELVE_STATUS architecture block to show Copilot mapping + ten sandpit.
- Result: PASS
- Follow-up: Revert frontend/terminal.py and docs/AGENT_TWELVE_STATUS.md if rollback required.

- Audit ID: AUDIT-20260331-013849
- Time (UTC): 2026-03-31T01:38:49Z
- Actor: copilot
- Objective: Add selectable agent chat in shared thread
- Evidence: Updated /api/chat to route by selected agent with shared conversation_id and prior-thread context; added chat agent selector in terminal templates.
- Result: PASS
- Follow-up: Revert frontend/terminal.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

- Audit ID: AUDIT-20260331-014500
- Time (UTC): 2026-03-31T01:45:00Z
- Actor: copilot
- Objective: Add thread selector and multi-agent on/off chat toggles
- Evidence: Updated chat UI with thread picker/new thread and checkbox toggles; /api/chat now supports agents[] fanout on a shared conversation and returns per-agent responses.
- Result: PASS
- Follow-up: Revert frontend/terminal.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

- Audit ID: AUDIT-20260331-020311
- Time (UTC): 2026-03-31T02:03:11Z
- Actor: copilot
- Objective: Tune local model residency and RAM-aware routing
- Evidence: Added Ollama keep_alive policy (Gemma/LLaMA warm, Qwen short-lived) and RAM-aware routing fallback from both->llama when free memory is low (non-debate).
- Result: PASS
- Follow-up: Revert core/pipeline/orchestrator.py.

- Audit ID: AUDIT-20260331-021518
- Time (UTC): 2026-03-31T02:15:18Z
- Actor: copilot
- Objective: Add organic chat UX + Duck/Sniffles controls
- Evidence: Added Duck/Sniffles chat toggles, Sniffles non-persistent behavior, conversational bubble UI with reactions/reply/ask-another actions, and audit-agent routing safeguards for responsiveness.
- Result: PASS
- Follow-up: Revert frontend/terminal.py, core/pipeline/orchestrator.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

- Audit ID: AUDIT-20260331-021925
- Time (UTC): 2026-03-31T02:19:25Z
- Actor: copilot
- Objective: Enable persistent Sniffles residency trial
- Evidence: Set Sniffles keep_alive default to 30m and adjusted chat timeout windows for Sniffles-only calls; verified model remains resident in ollama ps under memory pressure.
- Result: PASS
- Follow-up: Revert core/pipeline/orchestrator.py, frontend/terminal.py.

- Audit ID: AUDIT-20260331-022336
- Time (UTC): 2026-03-31T02:23:36Z
- Actor: copilot
- Objective: Add chat loading bars with learned ETA
- Evidence: Added per-agent elapsed_ms telemetry and chat loading bars with ETA estimates based on moving-average latency per agent (saved in localStorage).
- Result: PASS
- Follow-up: Revert frontend/terminal.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

- Audit ID: AUDIT-20260331-023610
- Time (UTC): 2026-03-31T02:36:10Z
- Actor: copilot
- Objective: Docked right-side tiles, full-edge resize, persistent chat threads
- Evidence: Implemented right-side docked tile behavior with pop-out control, edge/corner resize handles, persistent active chat thread restore, and visible thread rail in chat pane.
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html.

- Audit ID: AUDIT-20260331-024538
- Time (UTC): 2026-03-31T02:45:38Z
- Actor: copilot
- Objective: Enabled safe SKILL command execution in Fridays chat
- Evidence: Added SKILL and /skill command parsing in /api/chat, routed to fridays.skills with trust-level ALM gating for mutating skills, and improved chat UI error handling for non-OK API responses.
- Result: PASS
- Follow-up: Revert frontend/terminal.py and frontend/templates/terminal_base.html.

- Audit ID: AUDIT-20260331-025850
- Time (UTC): 2026-03-31T02:58:50Z
- Actor: copilot
- Objective: Added user profiles, proxy identity, and per-skill authorization controls
- Evidence: Implemented DB-backed user_profiles + user_skill_permissions, auth/profile/permissions APIs, identity-aware chat skill execution, and Skills-window permission management with top-right identity indicator and proxy switching.
- Result: PASS
- Follow-up: Revert frontend/terminal.py utils/database.py frontend/templates/terminal_base.html.

