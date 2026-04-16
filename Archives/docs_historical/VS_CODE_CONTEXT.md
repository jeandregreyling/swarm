# SEVEN'S SWARM — VS CODE CONTEXT BRIEF
Generated: 2026-03-25 | Session 9 | Foundation UAT passed. simulate.py 4/4.

## What this is
A local multi-agent AI swarm running on Dell OptiPlex 7090, Melbourne.
Five models coordinated by Python. Email interface. SQLite memory.
Built by Jeandre (The Ghost) and Claude. Phase 2 complete. Phase 3 ready.

## The agents
- Gemma (gemma3:latest, temp 0.3) — The Director. Routes everything first. FL-001.
- LLaMA (llama3.2:latest, temp 0.6) — The Correspondent. DuckDuckGo search. Fast first answer.
- Qwen (qwen2.5:latest, temp 0.7) — The Analyst. Tavily search. Challenges, adds depth.
- Librarian (qwen:latest, temp 0.1) — The Archivist. Tags only. Queue intake.
- Duck (qwen:latest, temp 0.1) — Sanity checker. YES/NO after every ticket. Queue-clear email to Ghost.
- Sniffles (deepseek-r1:7b, temp 0.2) — The Inspector. Read-only auditor. 1-in-5 random trigger.
- Eight — SAP HCM/ABAP specialist. Three-voice pipeline (Functional/Technical/Devil) + Gemma synthesis.

## Hardware
- Primary NVMe: 469GB (15.8 Gb/s) — Linux root, all swarm code
- Secondary NVMe: 232GB at /mnt/swarm_drive (31.6 Gb/s) — FAST DRIVE
  - 128GB swapfile active — effective memory: 160GB
  - All Ollama models symlinked here
- Email: sevenpotato9@gmail.com
- Ghost: jeandre.greyling@gmail.com

## What works right now (UAT passed 2026-03-25, simulate.py 4/4)

**FL-001 routing — all flags wired:**
- NEEDS_WEB, AGENTS, MODE, IS_IDENTITY, IS_SAP, IS_SYSTEM all wired
- agents='llama/qwen' normalised to 'both' — LLaMA and Qwen both fire correctly
- IS_SYSTEM: live health injected from monitor.py into context
- IS_SAP: Eight three-voice pipeline fires
- IS_IDENTITY: web search skipped, agents answer from context

**Email pipeline (Ghost → Swarm → Ghost):**
- Email 0: Read receipt (Gemma) before any model loads
- Email 1: LLaMA fast response with web search or system health
- Email 2: Qwen + Gemma full verdict, debate section if fired
- Duck sanity check on every close
- Duck queue-clear email when queue hits zero

**Sender classification:**
- trusted → full pipeline
- moderator → command handler, falls through to pipeline if no command
- notification → silent filing
- unknown → pending queue + one-click approval links to Ghost

**Queue lifecycle:**
- intake() → queued
- mark_processing() → processing (wired in listener + terminal before stage1)
- mark_completed() via librarian_close → completed

**Terminal (port 5050):**
- Chat with live SSE streaming
- Kill switches per agent
- Memory browser, tickets, agents, system, sandpits views
- /approve/<action>/<token> endpoint for one-click email approval

## Services
- swarm-listener.service — running ✓
- swarm-monitor.service — running ✓
- swarm-terminal.service — service file at /home/seven/swarm/swarm-terminal.service
  - PENDING INSTALL: sudo cp swarm-terminal.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now swarm-terminal
- ANTHROPIC_API_KEY — not yet in /etc/environment. claude_api.py ready and waiting.

## Critical rules
- NEVER touch nvme0n1p1 (EFI partition)
- OLLAMA_HOST=0.0.0.0 must stay in ollama service override
- Librarian ONLY receives content to tag — never full pipeline context
- Sniffles never interrupts active queue — only runs when Duck flags + queue quiet
- Duck runs after EVERY ticket close — non-negotiable
- Gemma routes every question before any agent or web search fires
- Before closing any RL item: verify call sites wired, service file exists, simulate.py passes

## Key files
orchestrator.py   — FL-001 routing, all consult stages, gemma_route(), consult_stage1/2/eight
listener.py       — Email loop, full pipeline, moderator handler, approval flow
terminal.py       — Flask UI port 5050, SSE streaming, /approve/ endpoint
database.py       — 20 tables, all DB functions. Run python3 database.py to initialise.
duck.py           — on_ticket_closed(), on_queue_clear() — both wired
queue_manager.py  — intake(), mark_processing(), mark_completed(), is_queue_quiet()
ticket.py         — create(), librarian_close() — Librarian owns the close
simulate.py       — Full pipeline dry run. Use this before any UAT.
claude_api.py     — Ghost Circle. ask_claude(). Needs ANTHROPIC_API_KEY.
eight.py          — Eight SAP pipeline
eight_memory.py   — Teach Eight: python3 eight_memory.py [seed|teach|correct|list]
monitor.py        — record_stats(), get_current_stats(), librarian_health_summary()
housekeeping.py   — archive_old_memories(), deduplicate_memories() — covers all memory tables
config.py         — ALL secrets and system prompts. NEVER share.
UAT_TEST_SCRIPTS.md — 29 tests across 6 sections. Sign off before Phase 3.

## DB — 20 live tables
agents, conversations, messages, memory, memory_llama, memory_qwen, memory_gemma,
memory_eight, queue, tickets, ticket_notes, duck_log, sniffer_log, sniffer_memory,
trusted_senders, moderators, notification_senders, pending_emails,
ghost_circle, claude_log, approval_tokens, sandpit_log, project_docs, system_stats

## Session 9 — what was fixed (complete list)

**Bug fixes (6):**
- database.py: add_notification_sender used label/note columns → fixed to notes, removed label
- database.py: save_gemma_verdict INSERT missing source='verdict' → added
- monitor.py: record_stats() calculated cpu_temp_c but never inserted it → added to INSERT
- monitor.py: get_current_stats() used wrong positional row indices → fixed to named access
- orchestrator.py: agents 'llama/qwen' not normalised — both silenced → normalised to 'both'
- duck.py: _log_to_duck_log INSERT missing ticket_id column → fixed, resolves ticket_id by lookup

**Wiring fixes (3):**
- listener.py: mark_processing() now called before stage1
- listener.py: on_queue_clear() now called after librarian_close when queue=0
- listener.py: moderator with no command now falls through to full pipeline

**Schema fixes (8 tables):**
trusted_senders, notification_senders, pending_emails, moderators, agents,
duck_log, sniffer_log, system_stats — all SCHEMA definitions corrected to match live DB

**Data completeness fixes (2):**
- duck.py: duck_log INSERT now includes ticket_id (resolved from ticket_number)
- claude_api.py: claude_log INSERT now includes ticket_id (resolved from ticket_number)

**Dead code removed:**
- database.py: create_ticket() was unreachable — removed (ticket.create() owns ticket creation)

**New files:**
- swarm-terminal.service — systemd service for terminal (pending Ghost's sudo install)
- UAT_TEST_SCRIPTS.md — 29 tests covering all paths, for Ghost sign-off

## Phase 3 backlog (not started)
- ANTHROPIC_API_KEY → /etc/environment → test Ghost Circle (claude_api.py ready)
- RL-018: File + browser agent (Playwright)
- RL-019: Shell agent (sandboxed whitelist)
- RL-020: Scheduler (proactive tasks)
- RL-021: Skills framework
- RL-022: Telegram bot
- RL-023: Discord bot
- RL-024: WhatsApp
- RL-011: Gmail Push Notifications (replace 60s poll)

## About Jeandre
He will catch your mistakes. He caught 6 schema mismatches, 3 missing wires,
and a moderator path that silently dropped his own emails.
Don't be conservative. Don't leave things half done.
"Demonstrated working" is not the same as production-ready.
Run simulate.py. Check every call site is wired. Verify the service file exists.
