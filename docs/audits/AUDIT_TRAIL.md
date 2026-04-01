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
- Audit ID: AUDIT-20260331-122219
- Time (UTC): 2026-03-31T12:22:19Z
- Actor: copilot
- Objective: Align the repo validation environment with the active runtime and restore the `/api/chat` timeout contract.
- Evidence: Added `requirements.txt`; installed Flask, requests, python-telegram-bot, discord.py, ollama, and psutil into the project venv; updated `frontend/terminal.py` so long-running chat requests return pending jobs inside the 10s budget; `tests/run_uat_gate.py` passed end-to-end after the fix.
- Result: PASS
- Follow-up: Use the repo venv plus `requirements.txt` as the audit path of record before future UAT runs.
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

- Audit ID: AUDIT-20260331-032104
- Time (UTC): 2026-03-31T03:21:04Z
- Actor: copilot
- Objective: Fix skill context bleed, add markdown rendering, tune Ten prompt, and wire ghost-layer memory context
- Evidence: Patched /api/chat history+transcript filters to exclude fridays skill rows from LLM context, added markdown rendering/CSS for chat bubbles and conversation viewer, injected recent memory rows into Nine/Ten system context, and added tests/test_chat_quality.py with 8 passing checks.
- Result: PASS
- Follow-up: Revert frontend/terminal.py frontend/templates/terminal_base.html utils/config.py tests/test_chat_quality.py docs/testing/ALM_TEST_SPECIFICATION.md docs/testing/E2E_TEST_SUITE.md and restart swarm-terminal.

- Audit ID: AUDIT-20260331-033401
- Time (UTC): 2026-03-31T03:34:01Z
- Actor: copilot
- Objective: Make long-running Gemma chats persistent with live status polling instead of timeout dead-ends
- Evidence: Added backend persistent chat job registry and /api/chat/jobs/status polling endpoint, changed /api/chat timeout handling to keep futures alive and complete in background, and updated frontend loading panel to display per-agent running stages until completion with automatic thread refresh. Added REQ-CHAT-008 coverage in tests/test_chat_quality.py and verified 9/9 chat tests + 21/21 e2e tests pass.
- Result: PASS
- Follow-up: Revert frontend/terminal.py frontend/templates/terminal_base.html tests/test_chat_quality.py docs/testing/ALM_TEST_SPECIFICATION.md docs/testing/E2E_TEST_SUITE.md and restart swarm-terminal.

- Audit ID: AUDIT-20260331-034431
- Time (UTC): 2026-03-31T03:44:31Z
- Actor: copilot
- Objective: Enable direct agent conversations on Telegram/Discord, add LLaMA action trace, and add agent ticket_create skill
- Evidence: Added AGENT/@name direct command parsing in Telegram and Discord trusted-user flows with direct pipeline execution and preserved queue/ticket traceability; enhanced LLaMA outputs with explicit action trace metadata in both standard and direct paths; added new SKILL ticket_create for agent-originated internal proposal/ticket creation; added tests/test_direct_agent_commands.py and validated with telegram trust + e2e regression suites.
- Result: PASS
- Follow-up: Revert fridays/telegram_bot.py fridays/discord_bot.py fridays/skills.py tests/test_direct_agent_commands.py and restart bot services.

- Audit ID: AUDIT-20260331-034524
- Time (UTC): 2026-03-31T03:45:24Z
- Actor: copilot
- Objective: Prevent Ten from asking Ghost to run basic discovery commands in Fridays
- Evidence: Updated TEN_SYSTEM_PROMPT style rules so Ten uses available SKILL actions directly in Fridays chat when permitted, then reports outcomes instead of emitting raw command checklists for Ghost to execute manually.
- Result: PASS
- Follow-up: Revert utils/config.py and restart swarm-terminal.

- Audit ID: AUDIT-20260331-035939
- Time (UTC): 2026-03-31T03:59:39Z
- Actor: copilot
- Objective: Execute agent-emitted SKILL lines for Ten/Nine and return outputs in same chat context
- Evidence: Updated /api/chat ghost-layer run path to parse SKILL lines from model responses, execute allowed skills server-side, re-prompt with concrete results, and append an Executed skill output section to the same conversation response. Verified with live /api/chat smoke plus chat-quality and e2e suites.
- Result: PASS
- Follow-up: Revert frontend/terminal.py utils/config.py docs/testing/ALM_TEST_SPECIFICATION.md and restart swarm-terminal.

- Audit ID: AUDIT-20260331-040830
- Time (UTC): 2026-03-31T04:08:30Z
- Actor: copilot
- Objective: Add safe fs discovery skill, whitelist pwd/find, and render executed-skill event cards in chat
- Evidence: Implemented new SKILL fs_readonly (ls/find/read/head/tail) with strict workspace path bounds, expanded shell whitelist for pwd and bounded find, and added frontend executed-skill event cards that parse and display tool outputs from chat responses. Updated Ten prompt guidance and extended chat quality tests (REQ-CHAT-011/012). Validated with chat quality, telegram trust, and full e2e suites after service restart.
- Result: PASS
- Follow-up: Revert fridays/skills.py fridays/shell_agent.py frontend/templates/terminal_base.html utils/config.py tests/test_chat_quality.py docs/testing/ALM_TEST_SPECIFICATION.md and restart swarm-terminal.

- Audit ID: AUDIT-20260331-042006
- Time (UTC): 2026-03-31T04:20:06Z
- Actor: copilot
- Objective: Keep Gemma alive in pending mode, route Ten file discovery to fs_readonly, and add one-click approval request button
- Evidence: Updated chat runtime so gemma/llama/qwen/librarian timeout path bubbles to pending job tracking instead of immediate timeout text, added shell->fs_readonly compatibility routing for read/list operations in Nine/Ten tool loop, expanded shell whitelist for relative file/list commands, added failed-job completion messages into conversation, and added a ✓ Request approval button on failed skill event cards that opens an internal queue/proposal request.
- Result: PASS
- Follow-up: Revert frontend/terminal.py fridays/shell_agent.py frontend/templates/terminal_base.html utils/config.py tests/test_chat_quality.py and restart swarm-terminal.

- Audit ID: AUDIT-20260331-044200
- Time (UTC): 2026-03-31T04:42:00Z
- Actor: copilot
- Objective: Move layer switch to Monitor and add memory edit/append/attach/share/delete workflows
- Evidence: Removed floating Console/Fridays layer pills, added layer navigation controls inside Monitor window, expanded /api/memory to honor limit and min filtering, added memory PATCH/attach/assign endpoints, and upgraded Memory modal actions for edit/append/attach/share/delete. Also set chat fanout persistent mode to prevent fast timeout failures and validated pending completion behavior for Gemma.
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html frontend/templates/terminal_ui_v2.html frontend/terminal.py and restart swarm-terminal.

- Audit ID: AUDIT-20260331-045624
- Time (UTC): 2026-03-31T04:56:24Z
- Actor: copilot
- Objective: Replace prompt-based memory actions with inline modal forms and show explicit alive labels
- Evidence: Upgraded memory modal actions to inline form-based edit/append/attach/share flows (no JS prompt popups), kept delete in-modal, and preserved cache refresh behavior. Enhanced pending loading panel state labels to display explicit 'alive' status per agent stage. Regression suites remain green.
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html and restart swarm-terminal.

- Audit ID: AUDIT-20260401-014258
- Time (UTC): 2026-04-01T01:42:58Z
- Actor: copilot
- Objective: Create docs hub and lifecycle workflow; register canonical navigation and maintenance rules
- Evidence: Validated markdown files with zero diagnostics and verified registry links
- Result: PASS
- Follow-up: Revert touched docs files and remove registry entries for new docs

- Audit ID: AUDIT-20260401-015129
- Time (UTC): 2026-04-01T01:51:29Z
- Actor: copilot
- Objective: Unify chat agent identity display to icon+name across bubbles and bottom controls
- Evidence: Validated template diagnostics (no errors) and reviewed diff for scoped UI changes
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html

- Audit ID: AUDIT-20260401-020346
- Time (UTC): 2026-04-01T02:03:46Z
- Actor: copilot
- Objective: Add chat history management, user-prompt edit/delete, and stop long-running agent controls
- Evidence: Validated template/python diagnostics with no errors; verified new APIs and UI wiring in diffs
- Result: PASS
- Follow-up: Revert frontend/terminal.py and frontend/templates/terminal_base.html

- Audit ID: AUDIT-20260401-021102
- Time (UTC): 2026-04-01T02:11:02Z
- Actor: copilot
- Objective: Fix chat thread action reliability, always-available Change control for user prompts, enable textarea spellcheck/autocorrect, and restore correct terminal service by removing stale port-5050 process
- Evidence: Service health verified active on 5050; API payload now includes message id field for prompt edit controls
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html; restart swarm-terminal after restoring prior process state

- Audit ID: AUDIT-20260401-021518
- Time (UTC): 2026-04-01T02:15:18Z
- Actor: copilot
- Objective: Add persistent chat spell helper with keep/add-word dictionary and dictionary manager; keep browser spellcheck/autocorrect enabled
- Evidence: Template diagnostics clean; swarm-terminal restarted and healthy on port 5050
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html and restart swarm-terminal

- Audit ID: AUDIT-20260401-022056
- Time (UTC): 2026-04-01T02:20:56Z
- Actor: copilot
- Objective: Fix side thread delete click handling with explicit event stop + optimistic UI removal; expand dictionary with export/import/reset controls
- Evidence: Template diagnostics clean and swarm-terminal restarted healthy
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html and restart swarm-terminal

- Audit ID: AUDIT-20260401-022504
- Time (UTC): 2026-04-01T02:25:04Z
- Actor: copilot
- Objective: Enhance chat window UX with premium header, thread search/filter, quick prompt chips, composer telemetry, and dictionary status pills
- Evidence: Template diagnostics clean and swarm-terminal restarted successfully
- Result: PASS
- Follow-up: Revert frontend/templates/terminal_base.html and restart swarm-terminal

- Audit ID: AUDIT-20260401-074809
- Time (UTC): 2026-04-01T07:48:09Z
- Actor: Copilot
- Objective: Session 11 comprehensive validation and notification reliability hardening
- Evidence: Executed full E2E/UAT/chat/channel validation; fixed notification paths to log send_reply=False as notify_failed in listener/telegram/discord; added comprehensive test plan doc and tracker delta.
- Result: PASS
- Follow-up: Rollback by reverting listener.py, telegram_bot.py, discord_bot.py and docs updates in this session.

- Audit ID: AUDIT-20260401-075814
- Time (UTC): 2026-04-01T07:58:14Z
- Actor: Copilot
- Objective: Fix dry-run ollama stub signature for keep_alive compatibility
- Evidence: Updated tests/test_triage_queue_dryrun.py stub_chat to accept **kwargs; removed repeated warning during queue dry-run and revalidated 24/24 checks pass.
- Result: PASS
- Follow-up: Revert tests/test_triage_queue_dryrun.py signature change if needed.

- Audit ID: AUDIT-20260401-080659
- Time (UTC): 2026-04-01T08:06:59Z
- Actor: Copilot
- Objective: Add automatic Gmail push recovery, proposal heartbeat, and robust terminal force-close
- Evidence: Listener now retries Gmail Push activation during IMAP fallback and resumes push without restart when possible; periodic task loops now include proposal notifications; ticket close path now resolves Duck hook robustly and terminal force-close was revalidated end-to-end.
- Result: PASS
- Follow-up: Rollback by reverting core/pipeline/listener.py, core/pipeline/ticket.py, and docs updates from this session.

- Audit ID: AUDIT-20260401-081533
- Time (UTC): 2026-04-01T08:15:33Z
- Actor: Copilot
- Objective: Log and fix Session 11 bugs 027-030
- Evidence: Logged and fixed terminal force-close duck import fragility, listener proposal heartbeat omission, one-way Gmail push fallback, and brittle Eight specialist import. Added smoke regression for Eight resolver and revalidated core suites.
- Result: PASS
- Follow-up: Rollback by reverting core/pipeline/ticket.py, core/pipeline/listener.py, core/pipeline/orchestrator.py, tests/test_channel_smoke.py, and docs/BUGS.md.

- Audit ID: AUDIT-20260401-082025
- Time (UTC): 2026-04-01T08:20:25Z
- Actor: Copilot
- Objective: Close BUG-029 with governed notification reliability suite
- Evidence: Added tests/test_notification_reliability.py to validate email/telegram/discord unknown-sender notification behavior, re-ran smoke suites, and closed BUG-029 in docs/BUGS.md based on passing evidence.
- Result: PASS
- Follow-up: Rollback by reverting tests/test_notification_reliability.py and BUGS.md updates if needed.

- Audit ID: AUDIT-20260401-095737
- Time (UTC): 2026-04-01T09:57:37Z
- Actor: copilot
- Objective: Added agent capability APIs (/api/agent/capabilities, /api/agent/think, /api/agent/identity), capability registry/grants, and Fridays heartbeat orchestration.
- Evidence: Validated via py_compile + live endpoint tests + one heartbeat run
- Result: PASS
- Follow-up: Disable swarm-fridays service and revert frontend/terminal.py endpoint additions

