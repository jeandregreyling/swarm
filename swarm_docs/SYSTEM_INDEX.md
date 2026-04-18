# SYSTEM INDEX

*Auto-generated: 2026-04-18 13:15*


## Python Modules


### Utils

| File | Description |
|------|-------------|
| `utils/agent_coordination.py` | utils/agent_coordination.py — Agent self-coordination (A.2.3) |
| `utils/api_versioning.py` | utils/api_versioning.py — API version prefix support (R.5) |
| `utils/app_launcher.py` | app_launcher.py — Seven |
| `utils/brief_engine.py` | brief_engine.py — Seven's Swarm |
| `utils/change_logger.py` | change_logger.py — Seven's Swarm Time Wizard integration |
| `utils/circuit_breaker.py` | utils/circuit_breaker.py — Per-agent circuit breaker + health probe |
| `utils/claude_api.py` | claude_api.py — Seven's Swarm |
| `utils/config.py` | — |
| `utils/config_validator.py` | utils/config_validator.py — Configuration validation & node config (D.4) |
| `utils/convert_docs.py` | convert_docs.py — Seven's Swarm (RL-022 docs) |
| `utils/create_docs.py` | create_docs.py — generate swarm_docs/*.docx with real content. |
| `utils/database.py` | database.py — Seven's Swarm  (backward-compatible shim) |
| `utils/db/__init__.py` | db — Seven's Swarm database layer. |
| `utils/db/_connection.py` | db._connection — Shared database primitives. |
| `utils/db/_schema.py` | db._schema — Schema definition, initialisation, migrations, and seeding. |
| `utils/db/agents.py` | db.agents — Agent registry and capability management. |
| `utils/db/approvals.py` | db.approvals — Pending emails and approval tokens. |
| `utils/db/audit.py` | db.audit — Ghost circle and activity log. |
| `utils/db/auth.py` | db.auth — User profiles, skill permissions, trusted senders / domains, |
| `utils/db/chat.py` | db.chat — Conversations, messages, and chat job tracking. |
| `utils/db/knowledge.py` | utils/db/knowledge.py — Shared swarm knowledge base CRUD + event broadcasts (A.3) |
| `utils/db/memory.py` | db.memory — Shared memory, agent-specific memory, project docs. |
| `utils/db/node_skills.py` | utils.db.node_skills — Federated skill registry CRUD (D.2) |
| `utils/db/nodes.py` | utils/db/nodes.py — Node registration CRUD (A.4.5) |
| `utils/db/registry.py` | db.registry — Cached Agent Registry: single source of truth for all agent metadata. |
| `utils/db/research.py` | utils.db.research — Research session & evidence CRUD (B.1.2) |
| `utils/db/tickets.py` | db.tickets — Ticket CRUD, snooze, overdue, digest stats. |
| `utils/db/timeline.py` | utils/db/timeline.py — Conversation timeline writer. |
| `utils/db/tools.py` | utils.db.tools — Tool build registry CRUD (C.1.2) |
| `utils/git_commit_logger.py` | git_commit_logger.py — Seven's Swarm Time Wizard git hook |
| `utils/governance.py` | utils/governance.py — Central proposal governance engine. |
| `utils/load_project_docs.py` | load_project_docs.py — Seven's Swarm |
| `utils/node_discovery.py` | utils/node_discovery.py — Node discovery + heartbeat + event relay (A.5.1, D.2, D.3) |
| `utils/proposal_review.py` | proposal_review.py — Duck's proposal sanity-check + chat-thread notification. |
| `utils/rate_limiter.py` | utils/rate_limiter.py — Token-bucket rate limiter middleware (E.1.2) |
| `utils/resource_gate.py` | utils/resource_gate.py — Ollama model resource gate |
| `utils/response_cache.py` | utils/response_cache.py — Simple TTL cache for Flask JSON responses (E.2.3) |
| `utils/sandpits.py` | sandpits.py — Fridays / Seven's Swarm |
| `utils/scheduler.py` | scheduler.py — Seven's Swarm Scheduler |
| `utils/security_headers.py` | utils/security_headers.py — Security headers + input validation middleware (E.1) |
| `utils/session_auth.py` | utils/session_auth.py — Session-based UI authentication (R.1) |
| `utils/seven_fridays.py` | seven_fridays.py — Developer Agent REPL (Agent 11 interface) |
| `utils/simulate.py` | simulate.py — Seven's Swarm |
| `utils/skills.py` | skills.py — Seven's Swarm Skills Framework |
| `utils/structured_logger.py` | utils/structured_logger.py — JSON structured logging (E.3.1) |
| `utils/swarm_bus.py` | utils/swarm_bus.py — Lightweight internal message bus (A.4.2) |
| `utils/swarm_root.py` | utils/swarm_root.py — Central SWARM_ROOT resolution (A.6.3) |
| `utils/swarm_tasks.py` | swarm_tasks.py — Seven's Swarm |
| `utils/vs_tools.py` | vs_tools.py — VS tab file read/memory tools for Nine |

### Core

| File | Description |
|------|-------------|
| `core/kill_switch.py` | KILL SWITCHES — Emergency control agents via Telegram/Discord |
| `core/pipeline/debate.py` | — |
| `core/pipeline/listener.py` | listener.py — Seven's Swarm |
| `core/pipeline/orchestrator.py` | — |
| `core/pipeline/queue_manager.py` | queue_manager.py — Seven's Swarm |
| `core/pipeline/ticket.py` | ticket.py — Seven's Swarm |
| `core/time_machine.py` | TIME MACHINE — Agent Twelve's Core Capability |

### Agent Modules

| File | Description |
|------|-------------|
| `agents/deepseek_local/deepseek_local_agent.py` | agents/deepseek_local/deepseek_local_agent.py — DeepSeek R1 (local Ollama) |
| `agents/eight/eight_agent.py` | agents/eight/eight_agent.py — Eight |
| `agents/eleven/grok_agent.py` | # LINKED TO: utils/config.py — imports ELEVEN_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/gemma/gemma_agent.py` | agents/gemma/gemma_agent.py — Gemma (local Ollama) |
| `agents/ghost_coder/ghost_coder_agent.py` | agents/ghost_coder/ghost_coder_agent.py — Ghost Coder (Agent #17) |
| `agents/llama/llama_agent.py` | agents/llama/llama_agent.py — LLaMA (local Ollama) |
| `agents/lmstudio/lmstudio_agent.py` | agents/lmstudio/lmstudio_agent.py — LM Studio (local OpenAI-compatible) |
| `agents/mistral/mistral_agent.py` | # LINKED TO: utils/config.py — imports MISTRAL_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/nine/nine_agent.py` | # LINKED TO: utils/config.py — imports NINE_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/phi3/phi3_agent.py` | agents/phi3/phi3_agent.py — Phi-3 Mini (local Ollama) |
| `agents/qwen/qwen_agent.py` | agents/qwen/qwen_agent.py — Qwen (local Ollama) |
| `agents/scholar/scholar_agent.py` | # LINKED TO: utils/config.py — imports SCHOLAR_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/seeker/seeker_agent.py` | # LINKED TO: utils/config.py — imports SEEKER_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/ten/copilot_agent.py` | # LINKED TO: utils/config.py — imports TEN_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/thirteen/thirteen_agent.py` | # LINKED TO: utils/config.py — imports THIRTEEN_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/twelve/twelve_agent.py` | # LINKED TO: utils/config.py — imports TWELVE_SYSTEM_PROMPT (edit prompts there, not here) |

### Fridays / Skills

| File | Description |
|------|-------------|
| `fridays/__init__.py` | — |
| `fridays/browser_agent.py` | fridays/browser_agent.py — Seven's Swarm (RL-018) |
| `fridays/discord_bot.py` | fridays/discord_bot.py — Seven's Swarm (RL-023) |
| `fridays/file_agent.py` | fridays/file_agent.py — Seven's Swarm (RL-018) |
| `fridays/orchestrator.py` | fridays/orchestrator.py — Seven's Swarm |
| `fridays/research_workflow.py` | fridays/research_workflow.py — Multi-stage research orchestrator (B.2) |
| `fridays/scheduler.py` | scheduler.py — Seven's Swarm Scheduler |
| `fridays/shell_agent.py` | fridays/shell_agent.py — Seven's Swarm (RL-019) |
| `fridays/skills.py` | fridays/skills.py — Seven's Swarm (RL-021) |
| `fridays/telegram_bot.py` | fridays/telegram_bot.py — Seven's Swarm (RL-022) |
| `fridays/tool_builder.py` | fridays/tool_builder.py — Tool build pipeline orchestrator (C.2) |

### Lib

| File | Description |
|------|-------------|
| `lib/__init__.py` | — |
| `lib/email/email_cleaner.py` | — |
| `lib/email/email_handler.py` | — |
| `lib/email/gmail_auth.py` | gmail_auth.py — Seven's Swarm |
| `lib/email/gmail_push.py` | gmail_push.py — Seven's Swarm |
| `lib/knowledge/__init__.py` | — |
| `lib/knowledge/categories.py` | lib/knowledge/categories.py — Knowledge Library category tree. |
| `lib/knowledge/ingest.py` | lib/knowledge/ingest.py — Text chunking and Ollama embedding pipeline. |
| `lib/knowledge/retrieval.py` | lib/knowledge/retrieval.py — Semantic search over embedded knowledge chunks. |
| `lib/knowledge/seed.py` | lib/knowledge/seed.py — Built-in knowledge documents for the Library. |
| `lib/knowledge/sources/__init__.py` | — |
| `lib/knowledge/sources/email_parser.py` | lib/knowledge/sources/email_parser.py — Extract structured text from emails. |
| `lib/knowledge/sources/pdf_parser.py` | lib/knowledge/sources/pdf_parser.py — Extract text from PDF files. |
| `lib/knowledge/sources/text_parser.py` | lib/knowledge/sources/text_parser.py — Normalise pasted plain text. |
| `lib/knowledge/sources/url_fetcher.py` | lib/knowledge/sources/url_fetcher.py — Fetch a URL and extract plain text. |
| `lib/knowledge/store.py` | lib/knowledge/store.py — SQLite persistence for the Knowledge Library. |
| `lib/search/internet.py` | — |
| `lib/search/internet_serper.py` | internet_serper.py — Gemma's search engine / Seven's Swarm |
| `lib/search/internet_tavily.py` | internet_tavily.py — Qwen and Eight's search engine / Seven's Swarm |
| `lib/system/contradiction_check.py` | — |
| `lib/system/discord_notify.py` | discord_notify.py — Seven's Swarm |
| `lib/system/file_versioning.py` | file_versioning.py — Seven's Swarm File Versioning & Change Tracking |
| `lib/system/housekeeping.py` | — |
| `lib/system/logging_bridge.py` | logging_bridge.py — Seven's Swarm Unified Logging |
| `lib/system/monitor.py` | monitor.py — Seven's Swarm system monitor |
| `lib/system/system_clock.py` | system_clock.py — Seven's Swarm Unified Time Source |
| `lib/system/time_machine.py` | time_machine.py — Seven's Swarm Time Machine - Point-in-Time Restore System |

## Flask Blueprints

| Blueprint | Routes | Description |
|-----------|--------|-------------|
| `agent_api` | 10 | agent_api.py — Agent Self-Service API routes |
| `agents` | 28 | — |
| `auth` | 12 | auth.py — Auth & Senders routes |
| `auto_audit` | 2 | auto_audit.py — Periodic self-audit: pytest + basic lint checks. |
| `brief` | 3 | brief.py — Ghost Brief routes |
| `chat` | 4 | chat.py — Chat Engine routes |
| `conversations` | 9 | conversations.py — Conversations routes |
| `debates` | 5 | debates.py — Debates routes |
| `decisions` | 3 | decisions.py — Decisions & Timeline routes |
| `diamond` | 3 | frontend/blueprints/diamond.py — Diamond Layer governance API. |
| `docs` | 11 | docs.py — Docs & Project Files routes |
| `email_bp` | 5 | blueprints/email_bp.py — Email tile API |
| `exec_bp` | 4 | exec_bp.py — Ghost Exec routes |
| `git` | 6 | git.py — Git Operations routes |
| `idle_mgmt_bp` | 3 | idle_mgmt_bp.py — Idle-time self-management (Tier 4.5). |
| `kb` | 7 | kb.py — Knowledge Base routes |
| `killswitch` | 6 | killswitch.py — Kill Switches routes |
| `legacy` | 3 | legacy.py — Legacy Pipeline & Approval routes |
| `library` | 11 | frontend/blueprints/library.py — Knowledge Library API routes. |
| `localai` | 5 | blueprints/localai.py — Local AI status and proxy API |
| `memory` | 8 | memory.py — Memory routes |
| `metrics` | 2 | frontend/blueprints/metrics.py — Observability metrics endpoint (E.3.2) |
| `nine` | 4 | nine.py — Agent Nine routes |
| `node` | 11 | frontend/blueprints/node.py — Node registration + federation endpoints (A.4.5 + A.5) |
| `ollama` | 4 | ollama.py — Ollama Models routes |
| `onboarding` | 2 | frontend/blueprints/onboarding.py — Onboarding wizard API |
| `patterns_bp` | 2 | patterns_bp.py — Pattern learning API (Tier 4.2). |
| `personality_bp` | 4 | personality_bp.py — Agent personality + diary system (Tier 4.4). |
| `proposals` | 22 | — |
| `research` | 5 | frontend/blueprints/research.py — Research API (B.4.1) |
| `shell` | 17 | shell.py — Shell & Terminal routes |
| `sse` | 1 | frontend/blueprints/sse.py — Server-Sent Events stream (R.2) |
| `system` | 17 | system.py — System & Monitoring routes |
| `tickets` | 11 | tickets.py — Tickets routes |
| `time_wizard_bp` | 10 | time_wizard_bp.py — Time Wizard routes |
| `tools` | 7 | frontend/blueprints/tools.py — Tool Build API (C.4.1) |
| `vpn_bp` | 1 | vpn_bp.py — Tailscale / VPN status API for Fridays terminal. |
| `weather_bp` | 1 | weather_bp.py — Lightweight weather proxy for world clocks. |
| `workspace` | 10 | workspace.py — Workspace & Code Ops routes |

## JS View Modules

| Module | Size |
|--------|------|
| `access.js` | 74.6 KB |
| `agents-config.js` | 19.0 KB |
| `chat.js` | 235.0 KB |
| `conversations.js` | 12.0 KB |
| `diamond.js` | 19.7 KB |
| `docs.js` | 30.2 KB |
| `email.js` | 22.4 KB |
| `files.js` | 42.0 KB |
| `fridays.js` | 7.0 KB |
| `git.js` | 23.7 KB |
| `home-chat.js` | 18.7 KB |
| `knowledge.js` | 5.8 KB |
| `library.js` | 22.0 KB |
| `localai.js` | 8.5 KB |
| `memory-landscape.js` | 9.6 KB |
| `memory.js` | 30.0 KB |
| `monitor.js` | 15.4 KB |
| `ollama.js` | 4.1 KB |
| `onboarding.js` | 16.2 KB |
| `services.js` | 4.7 KB |
| `skills.js` | 25.7 KB |
| `studio.js` | 84.3 KB |
| `terminal-commands.js` | 13.0 KB |
| `terminal.js` | 41.3 KB |
| `tickets.js` | 6.7 KB |
| `time-wizard.js` | 36.1 KB |
| `trace.js` | 17.5 KB |
| `vpn.js` | 4.2 KB |

## Database Tables

| Table | Rows |
|-------|------|
| `activity_log` | 22048 |
| `agent_capabilities` | 169 |
| `agent_diary` | 0 |
| `agent_skills` | 10 |
| `agents` | 19 |
| `approval_tokens` | 160 |
| `audit_results` | 3 |
| `chat_jobs` | 283 |
| `claude_log` | 1 |
| `conv_timeline` | 675 |
| `conversations` | 28 |
| `daily_checkpoint` | 0 |
| `daily_checkpoints` | 0 |
| `debate_turns` | 0 |
| `debates` | 0 |
| `decisions` | 1732 |
| `deferred_items` | 0 |
| `duck_log` | 481 |
| `file_versions` | 4 |
| `file_writes` | 4 |
| `ghost_briefs` | 101 |
| `ghost_circle` | 2404 |
| `governance_log` | 73 |
| `knowledge_chunks` | 371 |
| `knowledge_sources` | 29 |
| `memory` | 2 |
| `memory_eight` | 0 |
| `memory_gemma` | 0 |
| `memory_ghost_coder` | 0 |
| `memory_grok` | 0 |
| `memory_llama` | 0 |
| `memory_mistral` | 0 |
| `memory_nine` | 1 |
| `memory_qwen` | 0 |
| `memory_scholar` | 0 |
| `memory_seeker` | 0 |
| `memory_sonic` | 0 |
| `memory_ten` | 0 |
| `memory_thirteen` | 0 |
| `memory_twelve` | 0 |
| `messages` | 57 |
| `moderators` | 2 |
| `node_config` | 0 |
| `node_skills` | 0 |
| `notification_senders` | 8 |
| `pending_emails` | 8 |
| `project_doc_versions` | 56 |
| `project_docs` | 64 |
| `proposal_attachments` | 0 |
| `queue` | 929 |
| `research_evidence` | 0 |
| `research_sessions` | 0 |
| `sandpit_log` | 220 |
| `scheduled_tasks` | 2 |
| `skills` | 38 |
| `sniffer_log` | 232 |
| `sniffer_memory` | 0 |
| `snoozed_tickets` | 0 |
| `sqlite_sequence` | 59 |
| `sudo_command_whitelist` | 4 |
| `swarm_bus` | 73 |
| `swarm_event_acks` | 0 |
| `swarm_events` | 0 |
| `swarm_globals` | 3 |
| `swarm_knowledge` | 0 |
| `swarm_nodes` | 0 |
| `system_stats` | 6173 |
| `terminal_shortcuts` | 10 |
| `ticket_notes` | 235 |
| `tickets` | 243 |
| `time_checkpoints` | 1574 |
| `time_events` | 67776 |
| `time_journal` | 64977 |
| `time_machine` | 4771 |
| `tool_builds` | 0 |
| `trusted_domains` | 0 |
| `trusted_senders` | 10 |
| `user_profiles` | 19 |
| `user_skill_permissions` | 3 |
| `work_proposal_notes` | 5 |
| `work_proposals` | 6 |

## Agents

| Name | Model | Tier | Role | Enabled |
|------|-------|------|------|---------|
| `grok` | grok-api | local | RETIRED 2026-04-04 — alias consolidated into eleven (Agent 11) | ✅ |
| `ghost` | external | human | Human operator. Builds, approves, decides. Full system authority. | ✅ |
| `gemma` | gemma3:latest | local | Director — routes, synthesises, speaks last | ✅ |
| `llama` | llama3.2:latest | local | Correspondent — web search, fast first response | ✅ |
| `mistral` | mistral:latest | local | Analyst — deep reasoning, debates, challenges Two | ✅ |
| `qwen` | qwen2.5:latest | local | Deep Analyst — specialist depth, multilingual reasoning | ✅ |
| `librarian` | qwen:latest | local | Gatekeeper + Vortex — tags, queues, closes, checkpoints | ✅ |
| `duck` | qwen2.5:latest | local | Sanity checker — YES/NO after every ticket | ✅ |
| `sniffles` | deepseek-r1:7b | local | Inspector — memory auditor, read only, chain-of-thought | ✅ |
| `eight` | gemma4:26b | local | SAP specialist — three-voice debate (Functional/Technical/Devil) | ✅ |
| `nine` | llama-3.3-70b-versatile | paid | Developer Agent — system architect, proposals, Ghost One-directed execution | ✅ |
| `ten` | gpt-4o | paid | Developer Agent — software engineer, code quality, implementation | ✅ |
| `eleven` | grok-api | paid | Developer Agent — lateral thinker, creative synthesis, alternatives | ✅ |
| `twelve` | claude-haiku-4-5 | paid | Developer Agent — time wizard, session continuity, Vortex | ✅ |
| `thirteen` | meta-llama/Llama-3.3-70B-Instruct | free | Developer Agent — HuggingFace specialist (testing) | ✅ |
| `scholar` | gemini-2.0-flash | service | Research · Gemini | ✅ |
| `seeker` | tavily | service | Internet Search · Tavily | ✅ |
| `duck_ddg` | duckduckgo | service | Web Search · DuckDuckGo (no key) | ✅ |
| `ghost_coder` | claude-opus-4-20250514 | paid | Developer Agent — code-aware AI, reads/writes/patches code, bridges Copilot and Fridays | ✅ |

## Skills

| Skill | Description |
|-------|-------------|
| `agent_status` | Check operational status of agents (idle/busy/down/disabled). No args = all agents. With agent name = single agent. |
| `alm_complete` | Mark your own in_progress proposal as done (awaiting Ghost confirmation to close). |
| `alm_create_proposal` | Create an ALM work proposal/ticket. Accepts quoted title+description or <title> || <description>. |
| `alm_self_approve` | Self-approve your own proposal and set it to in_progress. Creates a Vortex checkpoint. No Ghost approval needed. |
| `alm_vortex` | Create a named Vortex (time machine) checkpoint. Call before making any file changes. |
| `browse` | Fetch a URL with headless Chromium. Returns page text. Needs a full URL — use search for questions. |
| `build_tool` | Scaffold a new tool from template. Types: script, skill, widget, cron, shell. Creates files + DB record. |
| `deep_dive` | Start a deep research investigation. 5+ sources, cross-validation, gap analysis. |
| `file_read` | Read a file from a sandpit. Format: agent/filename.txt |
| `file_write` | Write content to your sandpit. |
| `fs_patch` | Replace an exact string in a file (first occurrence). Safe targeted edit without full rewrite. |
| `fs_patch_lines` | Replace a line range in a file by line numbers. PREFERRED over fs_patch — no exact-match fragility. Read with fs_readonly lines first to get line numbers, then replace that range. |
| `fs_readonly` | Read-only filesystem helper for workspace discovery (ls/find/read/head/tail/lines). |
| `fs_verify` | Syntax-check a Python or JavaScript file after patching. ALWAYS run this after every fs_patch or fs_patch_lines call. |
| `fs_write` | Write (overwrite) any file within the swarm repo. Creates parent dirs as needed. |
| `housekeeping` | Run the Librarian housekeeping cycle: archive old memories, remove duplicates, trigger agent play time. |
| `knowledge_search` | Search the consultant knowledge library (SAP HCM, ABAP, emails, PDFs, SAP notes). |
| `knowledge_write` | Write a new entry to the shared swarm knowledge base. Governed: only from completed proposal context or ghost. |
| `list` | List all available skills. |
| `memory_search` | Search the swarm memory pools. Returns top matches. |
| `proposals` | Check sandpits/shared/proposals/ for new agent proposals and notify Ghost. |
| `remind` | Send Ghost an immediate plain-text reminder email. |
| `research` | Start a research session on a topic. Searches, analyses, and archives findings. Default depth: standard. |
| `research_resume` | Resume a paused research session. |
| `research_status` | Check the status and summary of a research session. |
| `schedule` | Create a scheduled task. Same syntax as SCHEDULE command. |
| `search` | DuckDuckGo web search. Returns top snippets. |
| `search_landscape` | Search the living system landscape JSON index (files, blueprints, tables, agents, skills). |
| `shell` | Run a whitelisted shell command. Output returned and emailed to Ghost. |
| `swarm_knowledge_search` | Search the shared swarm knowledge base (lessons, decisions, facts, patterns, warnings). |
| `system_index` | Generate or query the system index (modules, blueprints, tables, agents, skills). No args = regenerate. With args = search the index. |
| `ticket_create` | Create an internal ticket/proposal. Format: <title> || <description> |
| `tool_list` | List tool builds. Optionally filter by agent name. |
| `tool_status` | Check the status of a tool build (scaffolded/building/testing/passed/failed/registered). |
| `tool_test` | Run tests for a tool build. Discovers pytest test file or runs --dry-run. |
| `tool_validate` | Run syntax validation on a tool build (Python AST, node --check, bash -n). |
| `ui_css_edit_checklist` | Show the global checklist for correct UI/CSS edit workflow (selectors, patching, verification). |
| `update_landscape` | Regenerate the system landscape index (MD + JSON). Governed: requires trust_level 2. |
