# SYSTEM INDEX

*Auto-generated: 2026-05-10 22:03*


## Python Modules


### Utils

| File | Description |
|------|-------------|
| `utils/agent_coordination.py` | utils/agent_coordination.py — Agent self-coordination (A.2.3) |
| `utils/api_versioning.py` | utils/api_versioning.py — API version prefix support (R.5) |
| `utils/app_launcher.py` | app_launcher.py — Seven |
| `utils/brief_engine.py` | brief_engine.py — Seven's Swarm |
| `utils/change_logger.py` | change_logger.py — Seven's Swarm Time Wizard integration |
| `utils/ci_profile.py` | utils.ci_profile — CI-friendly no-network integration profile. |
| `utils/circuit_breaker.py` | utils/circuit_breaker.py — Per-agent circuit breaker + health probe |
| `utils/claude_api.py` | claude_api.py — Seven's Swarm |
| `utils/coding_bible.py` | utils/coding_bible.py — Coding Bible loader. |
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
| `utils/db/interests.py` | utils/db/interests.py — Phase 5: agent-facing interests CRUD with provenance. |
| `utils/db/knowledge.py` | utils/db/knowledge.py — Shared swarm knowledge base CRUD + event broadcasts (A.3) |
| `utils/db/memory.py` | db.memory — Shared memory, agent-specific memory, project docs. |
| `utils/db/node_skills.py` | utils.db.node_skills — Federated skill registry CRUD (D.2) |
| `utils/db/nodes.py` | utils/db/nodes.py — Node registration CRUD (A.4.5) |
| `utils/db/registry.py` | db.registry — Cached Agent Registry: single source of truth for all agent metadata. |
| `utils/db/research.py` | utils.db.research — Research session & evidence CRUD (B.1.2) |
| `utils/db/tickets.py` | db.tickets — Ticket CRUD, snooze, overdue, digest stats. |
| `utils/db/timeline.py` | utils/db/timeline.py — Conversation timeline writer. |
| `utils/db/tools.py` | utils.db.tools — Tool build registry CRUD (C.1.2) |
| `utils/db/trace_log.py` | utils/db/trace_log.py — Session 29 durable mirror for core.spine events. |
| `utils/db/watchdog_lessons.py` | Persistent Watchdog repair lessons. |
| `utils/git_commit_logger.py` | git_commit_logger.py — Seven's Swarm Time Wizard git hook |
| `utils/governance.py` | utils/governance.py — Central proposal governance engine. |
| `utils/intent_classifier.py` | Intent classifier for agentic chat routing (Phase 8.0). |
| `utils/load_project_docs.py` | load_project_docs.py — Seven's Swarm |
| `utils/meltdown_detector.py` | Meltdown detector — self-healing triage for the swarm. |
| `utils/model_selector.py` | Model selector for agentic chat routing (Phase 8.0 — Chunk 8E). |
| `utils/node_discovery.py` | utils/node_discovery.py — Node discovery + heartbeat + event relay (A.5.1, D.2, D.3) |
| `utils/notification_prefs.py` | Notification channel preferences (S-859446F555). |
| `utils/password.py` | utils.password — shared password hashing helpers. |
| `utils/platform_compat.py` | utils/platform_compat.py — Cross-platform guard helpers. |
| `utils/proposal_review.py` | proposal_review.py — Duck's proposal sanity-check + chat-thread notification. |
| `utils/rate_limiter.py` | utils/rate_limiter.py — Token-bucket rate limiter middleware (E.1.2) |
| `utils/resource_gate.py` | utils/resource_gate.py — Ollama model resource gate |
| `utils/response_cache.py` | utils/response_cache.py — Simple TTL cache for Flask JSON responses (E.2.3) |
| `utils/sandpits.py` | sandpits.py — Fridays / Seven's Swarm |
| `utils/scheduler.py` | scheduler.py — Seven's Swarm Scheduler |
| `utils/security_headers.py` | utils/security_headers.py — Security headers + input validation middleware (E.1) |
| `utils/service_heartbeat.py` | Service heartbeat helpers (S-E056DBAD19, S-B1279A66EB). |
| `utils/session_auth.py` | utils/session_auth.py — Session-based UI authentication (R.1) |
| `utils/seven_fridays.py` | — |
| `utils/simulate.py` | simulate.py — Seven's Swarm |
| `utils/skills.py` | skills.py — Seven's Swarm Skills Framework |
| `utils/structured_logger.py` | utils/structured_logger.py — JSON structured logging (E.3.1) |
| `utils/studio_intake.py` | Studio intake helpers. |
| `utils/swarm_bus.py` | utils/swarm_bus.py — Lightweight internal message bus (A.4.2) |
| `utils/swarm_root.py` | utils/swarm_root.py — Central SWARM_ROOT resolution (A.6.3) |
| `utils/swarm_tasks.py` | swarm_tasks.py — Seven's Swarm |
| `utils/tasker_run_lock.py` | utils.tasker_run_lock — per-task in-process lock for run-now actions. |
| `utils/vs_tools.py` | vs_tools.py — VS tab file read/memory tools for Nine |

### Core

| File | Description |
|------|-------------|
| `core/acceptance_gate.py` | core.acceptance_gate — final acceptance check for a project. |
| `core/agent_scorecards.py` | Durable capability scorecards for swarm agents. |
| `core/auth_2fa.py` | core/auth_2fa.py — TOTP 2-factor authentication primitives. |
| `core/auth_rate_limit.py` | core/auth_rate_limit.py — in-process rate limiter + audit log for /api/auth. |
| `core/chat_actions.py` | core/chat_actions.py — Pure-rules chat action detector ("Siri-but-better"). |
| `core/coding_bible_probe.py` | core.coding_bible_probe — runtime verification of Coding Bible fan-out. |
| `core/curiosity.py` | core/curiosity.py — PACKET-10B: Curiosity organ. |
| `core/fan_controller.py` | core/fan_controller.py — read-only fan / temperature monitor. |
| `core/feeds.py` | core.feeds — server-side feed subscription store + RSS fetcher. |
| `core/hive/__init__.py` | core.hive — cross-platform compute hive. |
| `core/hive/contract.py` | core.hive.contract — Node Resource Contract v0. |
| `core/hive/enrolment.py` | core.hive.enrolment — node tokens + handshake helpers. |
| `core/hive/local_node.py` | core.hive.local_node — telemetry for THIS host. |
| `core/hive/providers/__init__.py` | core.hive.providers — per-platform telemetry providers. |
| `core/hive/providers/android.py` | core.hive.providers.android — telemetry provider for Android (Termux). |
| `core/hive/providers/base.py` | core.hive.providers.base — provider abstract interface. |
| `core/hive/providers/generic.py` | core.hive.providers.generic — fallback provider for unknown platforms. |
| `core/hive/providers/linux.py` | core.hive.providers.linux — Linux telemetry provider. |
| `core/hive/providers/macos.py` | core.hive.providers.macos — Darwin telemetry provider. |
| `core/hive/providers/windows.py` | core.hive.providers.windows — Windows telemetry provider. |
| `core/hive/registry.py` | core.hive.registry — persistent node registry. |
| `core/hive/self_sampler.py` | core.hive.self_sampler — leader-side daemon that samples THIS host. |
| `core/hive/termux_runner.py` | core.hive.termux_runner — Python task executor for Android (Termux). |
| `core/integration_dashboard.py` | core.integration_dashboard — aggregate tile for the Studio |
| `core/interests_bridge.py` | core.interests_bridge — small surface for the Tasker UI bridge and |
| `core/kill_switch.py` | KILL SWITCHES — Emergency control agents via Telegram/Discord |
| `core/knowledge/__init__.py` | core.knowledge — Knowledge Center package. |
| `core/knowledge/close_out.py` | core.knowledge.close_out — ALM close-out report builder. |
| `core/knowledge/context_packs.py` | Compact project context packs for local agents and Studio previews. |
| `core/knowledge/projects.py` | core.knowledge.projects — Session 30.1: Projects, Steps, Test Cases. |
| `core/knowledge/scripts.py` | core.knowledge.scripts — Knowledge Center's test-lab script registry. |
| `core/knowledge/test_runs.py` | core.knowledge.test_runs — Session 30: ALM-style test run history. |
| `core/llm.py` | core/llm.py — Single Ollama gateway for the entire swarm. |
| `core/market_watch.py` | Money Hub newsletter generation. |
| `core/media_center/__init__.py` | — |
| `core/media_center/framework.py` | Media Center framework helpers. |
| `core/model_runtime_gateway.py` | Fridays-owned local model runtime gateway. |
| `core/notifications.py` | core/notifications.py — Shared notification formatter. |
| `core/pipeline/debate.py` | — |
| `core/pipeline/listener.py` | listener.py — Seven's Swarm |
| `core/pipeline/orchestrator.py` | — |
| `core/pipeline/queue_manager.py` | queue_manager.py — Seven's Swarm |
| `core/pipeline/ticket.py` | ticket.py — Seven's Swarm |
| `core/records/__init__.py` | core.records — Platinum layer per-record file storage + typed edges. |
| `core/records/attachments.py` | Content-addressed binary attachment store. |
| `core/records/links.py` | core.records.links — Platinum layer typed edges. |
| `core/records/promote.py` | core.records.promote — Platinum layer record morphing. |
| `core/records/store.py` | core.records.store — Platinum layer per-record file storage. |
| `core/records/xref.py` | core.records.xref — Platinum layer cross-reference builder. |
| `core/routing.py` | core/routing.py — Deterministic routing brain for Seven's Swarm. |
| `core/seven/__init__.py` | core.seven — Seven IS the system. |
| `core/seven/concepts.py` | core.seven.concepts — load Seven's self-knowledge from ``docs/seven/*.md``. |
| `core/seven/continuous.py` | core.seven.continuous — Seven's always-on learner. |
| `core/seven/memory.py` | core.seven.memory — Seven's three memory stores. |
| `core/seven/perception.py` | core.seven.perception — Seven's read-only view of the swarm. |
| `core/seven/reasoning.py` | core.seven.reasoning — Seven's small deterministic mind. |
| `core/seven/suggest.py` | core.seven.suggest — propose-only nudges built from a perception snapshot. |
| `core/seven_llm/__init__.py` | core.seven_llm — Seven Runtime model orchestration layer. |
| `core/seven_llm/driver_base.py` | core/llm/driver_base.py — Driver ABC. |
| `core/seven_llm/driver_llamacpp.py` | core/llm/driver_llamacpp.py — in-process llama-cpp-python driver. |
| `core/seven_llm/driver_lmstudio.py` | core/llm/driver_lmstudio.py — LM Studio HTTP driver (OpenAI-compatible). |
| `core/seven_llm/driver_ollama.py` | core/llm/driver_ollama.py — Ollama driver (feature-flagged SCOUT peer). |
| `core/seven_llm/driver_openai.py` | core/llm/driver_openai.py — OpenAI / Azure OpenAI / any OpenAI-compatible |
| `core/seven_llm/pool.py` | core/llm/pool.py — warm-pool with TTL, RAM ceiling, LRU eviction. |
| `core/seven_llm/registry.py` | core/llm/registry.py — Seven's own model catalogue. |
| `core/spine.py` | core/spine.py — Session 29: Seven-as-spine. |
| `core/swarm_platform.py` | core.swarm_platform — runtime capability detection for the swarm. |
| `core/testlab_registry.py` | core/testlab_registry.py — Session 28 Studio Test Lab |
| `core/time_machine.py` | TIME MACHINE — Agent Twelve's Core Capability |
| `core/vortex_health.py` | core/vortex_health.py — Stale-state probe for the Vortex (TimeMachine). |
| `core/watched_topics.py` | core.watched_topics — small helpers around the SAP/watched-topic stack. |
| `core/witness.py` | core/witness.py — Seven the Witness. |

### Agent Modules

| File | Description |
|------|-------------|
| `agents/deepseek_local/deepseek_local_agent.py` | agents/deepseek_local/deepseek_local_agent.py — DeepSeek R1 (local Ollama) |
| `agents/eight/eight_agent.py` | agents/eight/eight_agent.py — Gemma 4 (agent Eight) |
| `agents/eleven/grok_agent.py` | # LINKED TO: utils/config.py — imports ELEVEN_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/gemma/gemma_agent.py` | agents/gemma/gemma_agent.py — Gemma (local Ollama) |
| `agents/ghost_coder/ghost_coder_agent.py` | agents/ghost_coder/ghost_coder_agent.py — Ghost Coder (Agent #17) |
| `agents/llama/llama_agent.py` | agents/llama/llama_agent.py — LLaMA (local Ollama) |
| `agents/lmstudio/lmstudio_agent.py` | agents/lmstudio/lmstudio_agent.py — LM Studio (local OpenAI-compatible) |
| `agents/mistral/mistral_agent.py` | # LINKED TO: utils/config.py — imports MISTRAL_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/nine/nine_agent.py` | # LINKED TO: utils/config.py — imports NINE_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/nineteen/nineteen_agent.py` | # LINKED TO: utils/config.py — imports NINETEEN_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/phi3/phi3_agent.py` | agents/phi3/phi3_agent.py — Phi-3 Mini (local Ollama) |
| `agents/qwen/qwen_agent.py` | agents/qwen/qwen_agent.py — Qwen (local Ollama) |
| `agents/scholar/scholar_agent.py` | # LINKED TO: utils/config.py — imports SCHOLAR_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/seeker/seeker_agent.py` | # LINKED TO: utils/config.py — imports SEEKER_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/seven/seven_agent.py` | agents/seven/seven_agent.py — Seven |
| `agents/ten/copilot_agent.py` | # LINKED TO: utils/config.py — imports TEN_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/thirteen/thirteen_agent.py` | # LINKED TO: utils/config.py — imports THIRTEEN_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/twelve/twelve_agent.py` | # LINKED TO: utils/config.py — imports TWELVE_SYSTEM_PROMPT (edit prompts there, not here) |
| `agents/twenty/twenty_agent.py` | agents/twenty/twenty_agent.py - Twenty (Qwen3.6) |

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
| `fridays/task_runner.py` | fridays/task_runner.py — Python task runner registry for the Tasker. |
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
| `_pillar_store` | 0 | Shared storage helpers for the four wishlist pillars. |
| `agent_api` | 10 | agent_api.py — Agent Self-Service API routes |
| `agents` | 28 | — |
| `app_center` | 9 | app_center.py — App Center for mobile/tablet/desktop/web/game projects. |
| `auth` | 15 | auth.py — Auth & Senders routes |
| `auto_audit` | 2 | auto_audit.py — Periodic self-audit: pytest + basic lint checks. |
| `brief` | 3 | brief.py — Ghost Brief routes |
| `business_bp` | 6 | Business Centre pillar — accounting + payroll spine, everything else hangs off. |
| `chat` | 9 | chat.py — Chat Engine routes |
| `coding_bible` | 4 | blueprints/coding_bible.py — Coding Bible retrieval API. |
| `conversations` | 9 | conversations.py — Conversations routes |
| `council_bp` | 2 | Council API blueprint — serves Agent 20 output to the frontend. |
| `curiosity` | 7 | blueprints/curiosity.py — Curiosity organ HTTP surface. |
| `cybersecurity_bp` | 5 | Cyber Security pillar (Diamond layer). |
| `debates` | 5 | debates.py — Debates routes |
| `decisions` | 3 | decisions.py — Decisions & Timeline routes |
| `diamond` | 5 | frontend/blueprints/diamond.py — Diamond Layer governance API. |
| `docs` | 16 | docs.py — Docs & Project Files routes |
| `email_accounts` | 6 | frontend/blueprints/email_accounts.py — runtime email accounts registry. |
| `email_bp` | 5 | blueprints/email_bp.py — Email tile API |
| `enrollment` | 4 | frontend/blueprints/enrollment.py — user-account enrolment endpoints. |
| `exec_bp` | 4 | exec_bp.py — Ghost Exec routes |
| `fan` | 2 | blueprints/fan.py — CPU temperature + fan mode API. |
| `feeds_bp` | 5 | blueprints/feeds_bp.py — Feeds subscription CRUD + poll. |
| `financial_bp` | 5 | Financial Analytics pillar — investment-banking oriented. |
| `git` | 11 | git.py — Git Operations routes |
| `gmail_labels` | 2 | frontend/blueprints/gmail_labels.py — Gmail label sync for Email folders. |
| `health` | 2 | Unified system health aggregator. |
| `health_bp` | 4 | Health digest API blueprint — one-stop-shop system visibility. |
| `hive` | 0 | frontend.blueprints.hive — HTTP surface for the cross-platform Hive. |
| `idle_mgmt_bp` | 3 | idle_mgmt_bp.py — Idle-time self-management (Tier 4.5). |
| `interests_bp` | 3 | Interests engine — derives user interests from conversations + system memory. |
| `kb` | 7 | kb.py — Knowledge Base routes |
| `kc_overview` | 1 | kc_overview.py — KC introspection ("what does Swarm know?"). |
| `killswitch` | 6 | killswitch.py — Kill Switches routes |
| `knowledge_bp` | 49 | Knowledge Center blueprint. |
| `legacy` | 3 | legacy.py — Legacy Pipeline & Approval routes |
| `library` | 25 | frontend/blueprints/library.py — Knowledge Library API routes. |
| `localai` | 5 | blueprints/localai.py — Local AI status and proxy API |
| `login_bp` | 14 | login_bp.py — User login, registration, session management, and approval. |
| `media_bp` | 9 | Media Center API — consume/produce media with local runners. |
| `media_center` | 13 | Media Center API blueprint. |
| `media_curriculum` | 5 | media_curriculum.py — KC media topic ↔ tool curriculum + provenance. |
| `media_jobs` | 3 | media_jobs.py — queued execution for MusicGen / Stable Audio / ffmpeg / video graph. |
| `memory` | 8 | memory.py — Memory routes |
| `metrics` | 2 | frontend/blueprints/metrics.py — Observability metrics endpoint (E.3.2) |
| `nine` | 4 | nine.py — Agent Nine routes |
| `node` | 11 | frontend/blueprints/node.py — Node registration + federation endpoints (A.4.5 + A.5) |
| `ollama` | 15 | ollama.py — Ollama Models routes |
| `onboarding` | 2 | frontend/blueprints/onboarding.py — Onboarding wizard API |
| `orientation` | 3 | orientation.py — First-run orientation flag (Y.49 / STEP-DOCS-UX-BC3D33C260). |
| `patterns_bp` | 2 | patterns_bp.py — Pattern learning API (Tier 4.2). |
| `personality_bp` | 4 | personality_bp.py — Agent personality + diary system (Tier 4.4). |
| `proposals` | 14 | — |
| `proposals_attachments` | 4 | proposals_attachments.py — Attachment routes for work proposals. |
| `proposals_git` | 4 | proposals_git.py — Git operations for work proposals. |
| `research` | 5 | frontend/blueprints/research.py — Research API (B.4.1) |
| `seven_bp` | 15 | blueprints.seven_bp — HTTP surface for Seven (perception + brain). |
| `shell` | 18 | shell.py — Shell & Terminal routes |
| `spine_bp` | 3 | blueprints/spine_bp.py — Session 29: spine events API. |
| `sse` | 1 | frontend/blueprints/sse.py — Server-Sent Events stream (R.2) |
| `studio_evidence` | 2 | frontend/blueprints/studio_evidence.py — pin partial trails to Studio. |
| `synth_board` | 5 | Synth-board: node/patch-board music workspace persistence. |
| `sysmod` | 3 | frontend/blueprints/sysmod.py — settings-surface for the sysmod pack. |
| `system` | 17 | system.py — System & Monitoring routes |
| `tasker_bp` | 14 | tasker_bp.py — Scheduled tasks CRUD API for the Tasker UI. |
| `testlab_bp` | 2 | blueprints/testlab_bp.py — Studio Test Lab API (Session 28) |
| `tickets` | 11 | tickets.py — Tickets routes |
| `time_wizard_bp` | 10 | time_wizard_bp.py — Time Wizard routes |
| `tools` | 7 | frontend/blueprints/tools.py — Tool Build API (C.4.1) |
| `trading_bp` | 6 | Online Trading pillar. |
| `video_editor` | 6 | Video editor timeline persistence + render-job hand-off. |
| `voice` | 3 | blueprints/voice.py — Voice I/O endpoints. |
| `vpn_bp` | 1 | vpn_bp.py — Tailscale / VPN status API for Fridays terminal. |
| `weather_bp` | 1 | weather_bp.py — Lightweight weather proxy for world clocks. |
| `wishlist_bp` | 3 | Wishlist blueprint (S-45064ED6C5). |
| `wishlist_registry` | 1 | wishlist_registry.py — captured pillars ↔ live blueprints. |
| `workspace` | 10 | workspace.py — Workspace & Code Ops routes |

## JS View Modules

| Module | Size |
|--------|------|
| `access.js` | 114.8 KB |
| `chat.js` | 286.5 KB |
| `conversations.js` | 15.8 KB |
| `diamond.js` | 39.6 KB |
| `docs.js` | 24.6 KB |
| `email.js` | 47.8 KB |
| `files.js` | 47.6 KB |
| `git.js` | 30.9 KB |
| `guide.js` | 7.9 KB |
| `health-digest.js` | 8.2 KB |
| `hive-nodes.js` | 2.7 KB |
| `home-chat.js` | 66.2 KB |
| `home_banner.js` | 1.7 KB |
| `knowledge.js` | 26.6 KB |
| `library-graph.js` | 12.4 KB |
| `library.js` | 45.2 KB |
| `localai.js` | 30.0 KB |
| `media-center.js` | 51.3 KB |
| `media.js` | 9.8 KB |
| `memory-landscape.js` | 9.6 KB |
| `memory.js` | 30.3 KB |
| `money-hub.js` | 6.8 KB |
| `monitor.js` | 34.6 KB |
| `ollama.js` | 4.1 KB |
| `onboarding.js` | 18.2 KB |
| `orbs.js` | 93.0 KB |
| `orientation_card.js` | 2.3 KB |
| `pillar_live.js` | 13.1 KB |
| `potato-farm.js` | 9.7 KB |
| `projects.js` | 57.9 KB |
| `records-files.js` | 8.7 KB |
| `services.js` | 5.0 KB |
| `skills.js` | 26.2 KB |
| `spotlight.js` | 26.1 KB |
| `studio-media.js` | 18.4 KB |
| `studio-records.js` | 15.3 KB |
| `studio-testlab.js` | 26.7 KB |
| `studio.js` | 98.5 KB |
| `tasker.js` | 24.1 KB |
| `terminal-commands.js` | 17.6 KB |
| `terminal.js` | 50.8 KB |
| `tickets.js` | 6.0 KB |
| `time-wizard.js` | 59.7 KB |
| `trace.js` | 22.6 KB |
| `traced.js` | 5.8 KB |
| `vpn.js` | 4.2 KB |
| `wishlist.js` | 4.3 KB |

## Database Tables

| Table | Rows |
|-------|------|
| `activity_log` | 62579 |
| `agent_capabilities` | 169 |
| `agent_capability_scores` | 18 |
| `agent_diary` | 0 |
| `agent_skills` | 10 |
| `agents` | 22 |
| `app_builds` | 0 |
| `app_project_targets` | 0 |
| `app_projects` | 0 |
| `approval_tokens` | 794 |
| `audit_results` | 54 |
| `business_ledger` | 0 |
| `change_runs` | 45 |
| `chat_jobs` | 803 |
| `chat_relay_recoveries` | 75 |
| `claude_log` | 1 |
| `conv_timeline` | 4660 |
| `conversations` | 117 |
| `council_output` | 18685 |
| `curiosity_questions` | 5 |
| `cyber_audit_events` | 0 |
| `daily_checkpoint` | 0 |
| `daily_checkpoints` | 0 |
| `debate_turns` | 0 |
| `debates` | 0 |
| `decisions` | 93628 |
| `deferred_items` | 0 |
| `duck_log` | 1155 |
| `email_delivery_log` | 41 |
| `email_retry_queue` | 0 |
| `enrollment_invites` | 0 |
| `feed_subscriptions` | 43 |
| `file_versions` | 4 |
| `file_writes` | 4 |
| `financial_positions` | 0 |
| `ghost_briefs` | 101 |
| `ghost_circle` | 5404 |
| `gmail_labels_cache` | 0 |
| `governance_log` | 431 |
| `kc_media_curriculum` | 59 |
| `kc_media_trace` | 12 |
| `knowledge_chunks` | 1737 |
| `knowledge_sources` | 145 |
| `media_items` | 1 |
| `media_jobs` | 1 |
| `media_providers` | 7 |
| `media_runs` | 183 |
| `memory` | 171 |
| `memory_eight` | 2 |
| `memory_gemma` | 11 |
| `memory_ghost_coder` | 0 |
| `memory_grok` | 47 |
| `memory_llama` | 3 |
| `memory_mistral` | 2 |
| `memory_nine` | 1 |
| `memory_qwen` | 1 |
| `memory_scholar` | 0 |
| `memory_seeker` | 0 |
| `memory_sonic` | 0 |
| `memory_ten` | 64 |
| `memory_thirteen` | 0 |
| `memory_twelve` | 0 |
| `memory_twenty` | 484 |
| `messages` | 256 |
| `moderators` | 2 |
| `node_config` | 0 |
| `node_skills` | 0 |
| `notification_channel_prefs` | 0 |
| `notification_senders` | 10 |
| `orientation_seen` | 1 |
| `pending_emails` | 8 |
| `project_blackboard_notes` | 121 |
| `project_doc_versions` | 375 |
| `project_docs` | 319 |
| `project_step_deps` | 0 |
| `project_step_evidence` | 457 |
| `project_steps` | 1114 |
| `project_test_cases` | 483 |
| `projects` | 62 |
| `proposal_attachments` | 0 |
| `proposal_projects` | 23 |
| `queue` | 2118 |
| `research_evidence` | 1243 |
| `research_sessions` | 69 |
| `sandpit_log` | 644 |
| `scheduled_tasks` | 23 |
| `service_heartbeat` | 0 |
| `settings_email_account_prefs` | 1 |
| `settings_email_accounts` | 0 |
| `settings_sysmod` | 2 |
| `seven_attention` | 3590 |
| `seven_beliefs` | 8091 |
| `seven_callouts` | 9 |
| `seven_concepts` | 9 |
| `seven_episodes` | 18626 |
| `seven_learnings` | 1 |
| `seven_settings` | 0 |
| `skills` | 47 |
| `sniffer_log` | 232 |
| `sniffer_memory` | 0 |
| `snoozed_tickets` | 0 |
| `sqlite_sequence` | 81 |
| `studio_evidence` | 1 |
| `sudo_command_whitelist` | 5 |
| `swarm_bus` | 431 |
| `swarm_event_acks` | 399 |
| `swarm_events` | 67 |
| `swarm_globals` | 3 |
| `swarm_knowledge` | 67 |
| `swarm_nodes` | 0 |
| `synth_board_projects` | 24 |
| `synth_board_revisions` | 7 |
| `system_stats` | 12380 |
| `task_run_log` | 5108 |
| `terminal_shortcuts` | 16 |
| `test_run_artifacts` | 61 |
| `test_runs` | 201 |
| `ticket_notes` | 909 |
| `tickets` | 922 |
| `time_checkpoints` | 8228 |
| `time_events` | 155869 |
| `time_journal` | 145823 |
| `time_machine` | 8817 |
| `tool_builds` | 0 |
| `trace_events` | 8031 |
| `trading_signals` | 0 |
| `trusted_domains` | 0 |
| `trusted_senders` | 10 |
| `user_2fa` | 3 |
| `user_interests` | 88 |
| `user_patterns` | 3 |
| `user_profiles` | 23 |
| `user_sessions` | 29 |
| `user_skill_permissions` | 3 |
| `video_render_jobs` | 10 |
| `video_timelines` | 25 |
| `watchdog_repair_lessons` | 38 |
| `watched_topic_evidence` | 189 |
| `watched_topic_settings` | 0 |
| `watcher_topic_last_seen` | 0 |
| `work_proposal_notes` | 5 |
| `work_proposals` | 167 |

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
| `seven` | local-algorithm | local | Personal companion — loyal, thinks out loud | ✅ |
| `eight` | gemma4:26b | local | SAP specialist — three-voice debate (Functional/Technical/Devil) | ✅ |
| `nine` | llama-3.3-70b-versatile | paid | Developer Agent — system architect, proposals, Ghost One-directed execution | ✅ |
| `ten` | gpt-4o | paid | Developer Agent — software engineer, code quality, implementation | ✅ |
| `eleven` | grok-api | paid | Developer Agent — lateral thinker, creative synthesis, alternatives | ✅ |
| `twelve` | claude-haiku-4-5 | paid | Developer Agent — time wizard, session continuity, Vortex | ✅ |
| `thirteen` | meta-llama/Llama-3.3-70B-Instruct | free | Developer Agent — HuggingFace specialist (testing) | ✅ |
| `scholar` | gemini-2.0-flash | service | Research · Gemini | ✅ |
| `seeker` | tavily | service | Internet Search · Tavily | ✅ |
| `duck_ddg` | duckduckgo | service | Web Search · DuckDuckGo (no key) | ✅ |
| `ghost_coder` | gpt-5 | paid | Developer Agent — code-aware AI, reads/writes/patches code, bridges Copilot and Fridays | ✅ |
| `nineteen` | o4-mini | paid | developer | ✅ |
| `twenty` | qwen3.6:latest | local | Nervous system — observes, deliberates, suggests (no LLM) | ✅ |
| `sniffles` | deepseek-r1:7b | local | Inspector — memory auditor, read only, chain-of-thought | ✅ |

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
| `check_models` | List locally installed Ollama models with sizes. Use "new" to check Ollama registry for trending models. Use "update <model>" to pull latest. |
| `claude_code` | Run a prompt through the Claude Code CLI (non-interactive). Best for code generation, review, and analysis tasks. |
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
| `lmstudio` | Chat with whatever model is currently loaded in LM Studio (port 1234, OpenAI-compat API). |
| `memory_search` | Search the swarm memory pools. Returns top matches. |
| `ollama_web_fetch` | Fetch and return full page content from a URL via Ollama cloud API (requires OLLAMA_API_KEY). |
| `ollama_web_search` | Web search via Ollama cloud API (requires OLLAMA_API_KEY). Returns title, URL, and snippet per result. |
| `picoclaw` | Send a message to a PicoClaw agent (has exec, web_fetch, web_search, subagent, cron tools built in). Runs picoclaw agent -m. |
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
| `tasker_history` | Show recent task execution history — what ran, when, and the result. |
| `tasker_list` | List all scheduled tasks and registered Python tasks with their schedules and status. |
| `tasker_run` | Run a registered Python task immediately. Use tasker_list to see available tasks. |
| `ticket_create` | Create an internal ticket/proposal. Format: <title> || <description> |
| `tool_list` | List tool builds. Optionally filter by agent name. |
| `tool_status` | Check the status of a tool build (scaffolded/building/testing/passed/failed/registered). |
| `tool_test` | Run tests for a tool build. Discovers pytest test file or runs --dry-run. |
| `tool_validate` | Run syntax validation on a tool build (Python AST, node --check, bash -n). |
| `ui_css_edit_checklist` | Show the global checklist for correct UI/CSS edit workflow (selectors, patching, verification). |
| `update_landscape` | Regenerate the system landscape index (MD + JSON). Governed: requires trust_level 2. |
