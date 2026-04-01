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

- Time (UTC): 2026-03-31T01:45:00Z
- Actor: copilot
- Scope: fridays/chat-threads-agent-toggles
- Change: Add thread selector and multi-agent on/off chat toggles
- Validation: Updated chat UI with thread picker/new thread and checkbox toggles; /api/chat now supports agents[] fanout on a shared conversation and returns per-agent responses.
- Rollback: Revert frontend/terminal.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

- Time (UTC): 2026-03-31T02:03:11Z
- Actor: copilot
- Scope: orchestrator/local-model-residency-policy
- Change: Tune local model residency and RAM-aware routing
- Validation: Added Ollama keep_alive policy (Gemma/LLaMA warm, Qwen short-lived) and RAM-aware routing fallback from both->llama when free memory is low (non-debate).
- Rollback: Revert core/pipeline/orchestrator.py.

- Time (UTC): 2026-03-31T02:15:18Z
- Actor: copilot
- Scope: chat/organic-bubbles-duck-sniffles
- Change: Add organic chat UX + Duck/Sniffles controls
- Validation: Added Duck/Sniffles chat toggles, Sniffles non-persistent behavior, conversational bubble UI with reactions/reply/ask-another actions, and audit-agent routing safeguards for responsiveness.
- Rollback: Revert frontend/terminal.py, core/pipeline/orchestrator.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

- Time (UTC): 2026-03-31T02:19:25Z
- Actor: copilot
- Scope: chat/sniffles-persistent-trial
- Change: Enable persistent Sniffles residency trial
- Validation: Set Sniffles keep_alive default to 30m and adjusted chat timeout windows for Sniffles-only calls; verified model remains resident in ollama ps under memory pressure.
- Rollback: Revert core/pipeline/orchestrator.py, frontend/terminal.py.

- Time (UTC): 2026-03-31T02:23:36Z
- Actor: copilot
- Scope: chat/eta-loading-bars
- Change: Add chat loading bars with learned ETA
- Validation: Added per-agent elapsed_ms telemetry and chat loading bars with ETA estimates based on moving-average latency per agent (saved in localStorage).
- Rollback: Revert frontend/terminal.py, frontend/templates/terminal_base.html, frontend/templates/terminal.html.

- Time (UTC): 2026-03-31T02:36:10Z
- Actor: copilot
- Scope: ui/docked-tiles-thread-persistence
- Change: Docked right-side tiles, full-edge resize, persistent chat threads
- Validation: Implemented right-side docked tile behavior with pop-out control, edge/corner resize handles, persistent active chat thread restore, and visible thread rail in chat pane.
- Rollback: Revert frontend/templates/terminal_base.html.

- Time (UTC): 2026-03-31T02:45:38Z
- Actor: copilot
- Scope: chat/skill-bridge
- Change: Enabled safe SKILL command execution in Fridays chat
- Validation: Added SKILL and /skill command parsing in /api/chat, routed to fridays.skills with trust-level ALM gating for mutating skills, and improved chat UI error handling for non-OK API responses.
- Rollback: Revert frontend/terminal.py and frontend/templates/terminal_base.html.

- Time (UTC): 2026-03-31T02:58:50Z
- Actor: copilot
- Scope: identity/profiles-and-skill-permissions
- Change: Added user profiles, proxy identity, and per-skill authorization controls
- Validation: Implemented DB-backed user_profiles + user_skill_permissions, auth/profile/permissions APIs, identity-aware chat skill execution, and Skills-window permission management with top-right identity indicator and proxy switching.
- Rollback: Revert frontend/terminal.py utils/database.py frontend/templates/terminal_base.html.

- Time (UTC): 2026-03-31T03:21:04Z
- Actor: copilot
- Scope: fridays/chat-quality-hardening
- Change: Fix skill context bleed, add markdown rendering, tune Ten prompt, and wire ghost-layer memory context
- Validation: Patched /api/chat history+transcript filters to exclude fridays skill rows from LLM context, added markdown rendering/CSS for chat bubbles and conversation viewer, injected recent memory rows into Nine/Ten system context, and added tests/test_chat_quality.py with 8 passing checks.
- Rollback: Revert frontend/terminal.py frontend/templates/terminal_base.html utils/config.py tests/test_chat_quality.py docs/testing/ALM_TEST_SPECIFICATION.md docs/testing/E2E_TEST_SUITE.md and restart swarm-terminal.

- Time (UTC): 2026-03-31T03:34:01Z
- Actor: copilot
- Scope: fridays/persistent-chat-progress
- Change: Make long-running Gemma chats persistent with live status polling instead of timeout dead-ends
- Validation: Added backend persistent chat job registry and /api/chat/jobs/status polling endpoint, changed /api/chat timeout handling to keep futures alive and complete in background, and updated frontend loading panel to display per-agent running stages until completion with automatic thread refresh. Added REQ-CHAT-008 coverage in tests/test_chat_quality.py and verified 9/9 chat tests + 21/21 e2e tests pass.
- Rollback: Revert frontend/terminal.py frontend/templates/terminal_base.html tests/test_chat_quality.py docs/testing/ALM_TEST_SPECIFICATION.md docs/testing/E2E_TEST_SUITE.md and restart swarm-terminal.

- Time (UTC): 2026-03-31T03:44:31Z
- Actor: copilot
- Scope: fridays/direct-agent-routing-and-self-tickets
- Change: Enable direct agent conversations on Telegram/Discord, add LLaMA action trace, and add agent ticket_create skill
- Validation: Added AGENT/@name direct command parsing in Telegram and Discord trusted-user flows with direct pipeline execution and preserved queue/ticket traceability; enhanced LLaMA outputs with explicit action trace metadata in both standard and direct paths; added new SKILL ticket_create for agent-originated internal proposal/ticket creation; added tests/test_direct_agent_commands.py and validated with telegram trust + e2e regression suites.
- Rollback: Revert fridays/telegram_bot.py fridays/discord_bot.py fridays/skills.py tests/test_direct_agent_commands.py and restart bot services.

- Time (UTC): 2026-03-31T03:45:24Z
- Actor: copilot
- Scope: ghost-layer/ten-fridays-execution-behavior
- Change: Prevent Ten from asking Ghost to run basic discovery commands in Fridays
- Validation: Updated TEN_SYSTEM_PROMPT style rules so Ten uses available SKILL actions directly in Fridays chat when permitted, then reports outcomes instead of emitting raw command checklists for Ghost to execute manually.
- Rollback: Revert utils/config.py and restart swarm-terminal.

- Time (UTC): 2026-03-31T03:59:39Z
- Actor: copilot
- Scope: ghost-layer/chat-skill-loop-execution
- Change: Execute agent-emitted SKILL lines for Ten/Nine and return outputs in same chat context
- Validation: Updated /api/chat ghost-layer run path to parse SKILL lines from model responses, execute allowed skills server-side, re-prompt with concrete results, and append an Executed skill output section to the same conversation response. Verified with live /api/chat smoke plus chat-quality and e2e suites.
- Rollback: Revert frontend/terminal.py utils/config.py docs/testing/ALM_TEST_SPECIFICATION.md and restart swarm-terminal.

- Time (UTC): 2026-03-31T04:08:30Z
- Actor: copilot
- Scope: chat-fs-readonly-whitelist-ui-cards
- Change: Add safe fs discovery skill, whitelist pwd/find, and render executed-skill event cards in chat
- Validation: Implemented new SKILL fs_readonly (ls/find/read/head/tail) with strict workspace path bounds, expanded shell whitelist for pwd and bounded find, and added frontend executed-skill event cards that parse and display tool outputs from chat responses. Updated Ten prompt guidance and extended chat quality tests (REQ-CHAT-011/012). Validated with chat quality, telegram trust, and full e2e suites after service restart.
- Rollback: Revert fridays/skills.py fridays/shell_agent.py frontend/templates/terminal_base.html utils/config.py tests/test_chat_quality.py docs/testing/ALM_TEST_SPECIFICATION.md and restart swarm-terminal.

- Time (UTC): 2026-03-31T04:20:06Z
- Actor: copilot
- Scope: chat-alive-permission-flow-hardening
- Change: Keep Gemma alive in pending mode, route Ten file discovery to fs_readonly, and add one-click approval request button
- Validation: Updated chat runtime so gemma/llama/qwen/librarian timeout path bubbles to pending job tracking instead of immediate timeout text, added shell->fs_readonly compatibility routing for read/list operations in Nine/Ten tool loop, expanded shell whitelist for relative file/list commands, added failed-job completion messages into conversation, and added a ✓ Request approval button on failed skill event cards that opens an internal queue/proposal request.
- Rollback: Revert frontend/terminal.py fridays/shell_agent.py frontend/templates/terminal_base.html utils/config.py tests/test_chat_quality.py and restart swarm-terminal.

- Time (UTC): 2026-03-31T04:42:00Z
- Actor: copilot
- Scope: monitor-layer-controls-memory-crud
- Change: Move layer switch to Monitor and add memory edit/append/attach/share/delete workflows
- Validation: Removed floating Console/Fridays layer pills, added layer navigation controls inside Monitor window, expanded /api/memory to honor limit and min filtering, added memory PATCH/attach/assign endpoints, and upgraded Memory modal actions for edit/append/attach/share/delete. Also set chat fanout persistent mode to prevent fast timeout failures and validated pending completion behavior for Gemma.
- Rollback: Revert frontend/templates/terminal_base.html frontend/templates/terminal_ui_v2.html frontend/terminal.py and restart swarm-terminal.

- Time (UTC): 2026-03-31T04:56:24Z
- Actor: copilot
- Scope: inline-memory-forms-alive-label
- Change: Replace prompt-based memory actions with inline modal forms and show explicit alive labels
- Validation: Upgraded memory modal actions to inline form-based edit/append/attach/share flows (no JS prompt popups), kept delete in-modal, and preserved cache refresh behavior. Enhanced pending loading panel state labels to display explicit 'alive' status per agent stage. Regression suites remain green.
- Rollback: Revert frontend/templates/terminal_base.html and restart swarm-terminal.

- Time (UTC): 2026-04-01T01:42:58Z
- Actor: copilot
- Scope: docs/README.md, docs/runbooks/DOCUMENTATION_LIFECYCLE_WORKFLOW.md, docs/registry/FILE_REGISTRY.md, docs/DEVELOPER_WORKFLOW.md
- Change: Create docs hub and lifecycle workflow; register canonical navigation and maintenance rules
- Validation: Validated markdown files with zero diagnostics and verified registry links
- Rollback: Revert touched docs files and remove registry entries for new docs

- Time (UTC): 2026-04-01T01:51:29Z
- Actor: copilot
- Scope: frontend/templates/terminal_base.html
- Change: Unify chat agent identity display to icon+name across bubbles and bottom controls
- Validation: Validated template diagnostics (no errors) and reviewed diff for scoped UI changes
- Rollback: Revert frontend/templates/terminal_base.html

- Time (UTC): 2026-04-01T02:03:46Z
- Actor: copilot
- Scope: frontend/terminal.py, frontend/templates/terminal_base.html
- Change: Add chat history management, user-prompt edit/delete, and stop long-running agent controls
- Validation: Validated template/python diagnostics with no errors; verified new APIs and UI wiring in diffs
- Rollback: Revert frontend/terminal.py and frontend/templates/terminal_base.html

- Time (UTC): 2026-04-01T02:11:02Z
- Actor: copilot
- Scope: frontend/templates/terminal_base.html, ops(runtime) swarm-terminal process ownership
- Change: Fix chat thread action reliability, always-available Change control for user prompts, enable textarea spellcheck/autocorrect, and restore correct terminal service by removing stale port-5050 process
- Validation: Service health verified active on 5050; API payload now includes message id field for prompt edit controls
- Rollback: Revert frontend/templates/terminal_base.html; restart swarm-terminal after restoring prior process state

- Time (UTC): 2026-04-01T02:15:18Z
- Actor: copilot
- Scope: frontend/templates/terminal_base.html
- Change: Add persistent chat spell helper with keep/add-word dictionary and dictionary manager; keep browser spellcheck/autocorrect enabled
- Validation: Template diagnostics clean; swarm-terminal restarted and healthy on port 5050
- Rollback: Revert frontend/templates/terminal_base.html and restart swarm-terminal

- Time (UTC): 2026-04-01T02:20:56Z
- Actor: copilot
- Scope: frontend/templates/terminal_base.html
- Change: Fix side thread delete click handling with explicit event stop + optimistic UI removal; expand dictionary with export/import/reset controls
- Validation: Template diagnostics clean and swarm-terminal restarted healthy
- Rollback: Revert frontend/templates/terminal_base.html and restart swarm-terminal

- Time (UTC): 2026-04-01T02:25:04Z
- Actor: copilot
- Scope: frontend/templates/terminal_base.html
- Change: Enhance chat window UX with premium header, thread search/filter, quick prompt chips, composer telemetry, and dictionary status pills
- Validation: Template diagnostics clean and swarm-terminal restarted successfully
- Rollback: Revert frontend/templates/terminal_base.html and restart swarm-terminal

- Time (UTC): 2026-04-01T07:48:09Z
- Actor: Copilot
- Scope: validation+notifications
- Change: Session 11 comprehensive validation and notification reliability hardening
- Validation: Executed full E2E/UAT/chat/channel validation; fixed notification paths to log send_reply=False as notify_failed in listener/telegram/discord; added comprehensive test plan doc and tracker delta.
- Rollback: Rollback by reverting listener.py, telegram_bot.py, discord_bot.py and docs updates in this session.

