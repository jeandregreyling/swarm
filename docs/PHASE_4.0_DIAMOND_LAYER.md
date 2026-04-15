# Seven's Swarm – V3.1 Project Plan

## "Diamond Layer + Service Boundaries for Distributed Swarms"

**Version:** 1.1 (Final)  
**Date:** 15 April 2026  
**Status:** NOT STARTED  
**Owner:** Seven  
**Builder:** Agent 12 (Claude)

---

## Vision

A local-first, governance-first swarm that runs reliably on one machine today and
can be distributed across multiple machines (your upgrades + friends testing)
tomorrow. Every node follows the exact same structure, proposals are the single
source of truth, humans and agents collaborate under the same rules, and the entire
swarm learns collectively while remaining secure and traceable.

**Core Principle:**
Governance must be solid before distribution. The architecture must be designed for
distribution from day one — not bolted on later. We build the Diamond Layer with
clean service boundaries baked in, so when we go multi-node the transition is smooth
instead of painful.

---

## Why This Order (A → B → C) Is Non-Negotiable

1. **Governance (A) must come first.** Without it, adding research assistant or tool
   builder features will create chaos and breakage.
2. **Research Assistant / Learning Lab (B)** builds directly on the Diamond Layer.
3. **Tool Builder (C)** comes after B is stable.
4. **Distribution (D)** is prepared during A but activated later.

Delaying the fracture would make future distribution 3–5× harder. We do the hard
architectural work now while the codebase is still manageable.

---

## Foundation Already Built (Phases 1–5)

These are DONE and form the solid base for Phase 4.0:

| Component | Phase | Status |
|-----------|-------|--------|
| Agent Registry (cached, 11 accessors, invalidation) | P2 | ✅ Done |
| Circuit Breaker (3-state, per-agent, env-configurable) | P4 | ✅ Done |
| Health Probe (ollama.list() pre-dispatch) | P4 | ✅ Done |
| Stuck Job Sweep (daemon, 10min interval, 2hr max) | P4 | ✅ Done |
| Trace Troubleshooter (job_id, timeline, frontend) | P3b | ✅ Done |
| Local Agent Skill Routing (via .chat() → skills_loop) | P3a | ✅ Done |
| Model Discovery (/api/localai/available-models) | P5.1 | ✅ Done |
| Hot-Swap (/api/agents/hot-swap) | P5.2 | ✅ Done |
| Import/Export (/api/agents/export-all, /import) | P5.3 | ✅ Done |
| System Index Generator + SKILL | P5.4 | ✅ Done |
| Cross-Reference (tickets↔proposals↔conversations) | P5.5 | ✅ Done |
| Error Boundaries (consistent timeout handling) | P4 | ✅ Done |

---

## Known Critical Gaps (From 15 April 2026 Audit)

| Gap | Severity | Addressed In |
|-----|----------|--------------|
| Multiple in_progress proposals per agent | CRITICAL | A.1 |
| Vortex does not do real Git commits/tags | HIGH | A.1 |
| ALM gate is still optional | HIGH | A.1 |
| Trust levels in skills not enforced | HIGH | A.2 |
| No shared swarm memory / landscape | HIGH | A.3 |
| No agent availability / self-coordination | MEDIUM | A.2 |
| Trace does not auto-start on proposals | MEDIUM | A.1 |

---

## Phase A – Diamond Layer + Service Boundary Preparation (Weeks 1–7)

**Goal:** Build the central governance core while preparing clear service boundaries
so the system is ready for distribution without a painful rewrite later.

---

### A.1 — Proposal Engine + Governance Core (Weeks 1–2)

- Proposal singleton enforcement (max 1 in_progress per agent)
- Mandatory ALM gate — no bypassing, Duck sanity check always required
- Vortex real Git integration: `create_checkpoint()` does `git commit` + `git tag`,
  `restore_checkpoint()` does `git revert`
- Auto-Trace on every proposal lifecycle event (trace_id = proposal_id)
- Transition function: `transition_proposal(proposal_id, new_status, agent)` with
  full validation + optimistic locking

**Detailed sub-tasks:**

- [x] **A.1.1 — Proposal Singleton Enforcement**
  - Max 1 `in_progress` proposal per agent at any time
  - `transition_proposal(proposal_id, new_status, agent)` — central state machine
  - Validates: current → new status is legal, agent owns it, no collision
  - Optimistic locking: check-and-set with row version or timestamp
  - Location: new file `utils/governance.py`

- [x] **A.1.2 — Mandatory ALM Gate**
  - Remove the conditional check around `_alm_gate_or_response()` in services.py
  - ALM gate always enforced regardless of Time Wizard state
  - Duck sanity check called before any execution begins
  - If Duck is unavailable, proposal blocks (does not silently proceed)

- [x] **A.1.3 — Vortex Real Git Integration**
  - `create_checkpoint()` → `git add -A && git commit -m "..." && git tag vortex-{id}`
  - `restore_checkpoint()` → `git revert --no-commit {tag}..HEAD && git commit`
  - Auto-checkpoint on proposal status → `in_progress` and → `done`
  - Checkpoint metadata stored in `time_checkpoints` table (already exists)
  - Handle dirty working tree gracefully (stash/warn)

- [x] **A.1.4 — Auto-Trace on Proposal Lifecycle**
  - Every proposal state change writes to `conv_timeline`
  - Trace ID = proposal_id (reuse existing trace infrastructure from P3b)
  - Every skill call within a proposal context gets a timeline entry
  - Trace visible in Studio proposal detail panel (already has cross-ref badges)

**Test Phase A.1:**
- [ ] Unit: proposal singleton — attempt 2 concurrent in_progress, second must fail
- [ ] Unit: state machine — verify all legal/illegal transitions
- [ ] Unit: Vortex creates real git tag, restore reverts changes
- [ ] Integration: create proposal → approve → in_progress → auto-checkpoint created
- [ ] Integration: ALM gate blocks execution when Duck is down
- [ ] Manual: verify Studio shows trace events for a proposal lifecycle
- [ ] Compile check: all modified files pass `py_compile`
- [ ] Service restart: `sudo systemctl restart swarm-terminal-prod` — no crash

---

### A.2 — Skill Trust + Agent Awareness (Weeks 2–3)

- Enforce `trust_level` in `skills.call()` against agent role/tier from registry
- Wire `user_skill_permissions` table for overrides
- `GET /api/agents/status` — per-agent busy/idle/down state (from chat_jobs + circuit breaker)
- New `SKILL agent_status` so agents can self-coordinate before relaying
- Idle agents can claim pending proposals that match their role

**Detailed sub-tasks:**

- [x] **A.2.1 — Trust Level Enforcement**
  - In `skills.call()`: look up agent's tier/role from registry
  - Compare against skill's `trust_level` in REGISTRY
  - Block and log if agent tier < required trust_level
  - Mapping: tier `local` → max trust 1, tier `paid` → max trust 2, `ghost` → trust 4
  - Configurable override via `user_skill_permissions` table

- [x] **A.2.2 — Agent Status API**
  - `GET /api/agents/status` → per-agent: name, status (idle/busy/down/disabled),
    active_jobs, circuit_breaker_state, last_seen
  - Status derived from: chat_jobs (running = busy), circuit breaker (open = down),
    registry (enabled = disabled)
  - `SKILL agent_status [agent_name]` — agents can query this themselves

- [x] **A.2.3 — Agent Self-Coordination**
  - On relay handoff: agent checks target availability via agent_status before dispatch
  - If target busy/down: auto-reroute to next-best agent by role match from registry
  - Idle agents can claim queued proposals that match their role/capabilities
  - Claim mechanism: atomic UPDATE with WHERE status='pending' AND agent IS NULL

**Test Phase A.2:**
- [x] Unit: local agent blocked from trust_level 2+ skill
- [x] Unit: ghost can call any skill
- [x] Unit: user_skill_permissions override grants access
- [x] Integration: /api/agents/status returns correct busy/idle for running jobs
- [x] Integration: relay to down agent auto-reroutes to alternative
- [x] Integration: idle agent claims pending proposal
- [x] Compile check + service restart

---

### A.3 — Shared Memory + Living Landscape (Weeks 3–4)

- Central `swarm_knowledge` table (any agent reads, governed writes only)
- Auto-publish key learnings from every completed proposal
- Living `system_landscape.md` + JSON index (files, buttons, fields, SAP mappings, workflows)
- `SKILL search_landscape` and `SKILL update_landscape`
- Housekeeping agents (Llama + Gemma3) can maintain the map

**Detailed sub-tasks:**

- [x] **A.3.1 — Shared Knowledge Table**
  - New table: `swarm_knowledge` (id, key, content, source_agent, source_proposal_id,
    category, importance, created_at, updated_at)
  - Categories: `lesson`, `decision`, `fact`, `pattern`, `warning`
  - Any agent can read. Writes governed: only from completed proposal context or ghost
  - `SKILL knowledge_write <category> <content>` — governed
  - `SKILL knowledge_search <query>` — open (extends existing memory_search)

- [x] **A.3.2 — Auto-Publish from Proposals**
  - When proposal status → `done`: extract key learnings from the proposal's trace
  - Agent that completed the proposal writes a summary to swarm_knowledge
  - Summary includes: what changed, why, what was learned, what to avoid
  - Triggered automatically in the proposal transition function (A.1.1)

- [x] **A.3.3 — Living Landscape**
  - Extend system index generator to track: buttons, fields, workflows, SAP mappings
  - JSON version alongside MD (machine-queryable)
  - `SKILL search_landscape <query>` — fast grep over the JSON index
  - `SKILL update_landscape <path> <description>` — governed update
  - Housekeeping agents (Llama, Gemma3) scheduled to refresh quarterly

- [x] **A.3.4 — Memory Broadcast**
  - When swarm_knowledge gets a new entry: emit a lightweight event
  - Other agents see "new knowledge available" in their next prompt context
  - Implementation: `swarm_events` table (event_type, payload, created_at, consumed_by)
  - No real-time push needed yet — poll on next agent invocation

**Test Phase A.3:**
- [x] Unit: agent can read swarm_knowledge, write blocked outside proposal context
- [x] Unit: ghost can write directly
- [x] Integration: complete a proposal → swarm_knowledge entry auto-created
- [x] Integration: SKILL search_landscape finds known file/button/field
- [x] Integration: new knowledge entry creates event, another agent sees it
- [x] Manual: run landscape generator, verify JSON matches MD
- [x] Compile check + service restart

---

### A.4 — Service Boundary Preparation (Weeks 4–6)

This is the key step for the distributed future.

- Define clean API contracts for Chat, Studio, Proposals, Vortex, Governance
- Introduce lightweight message protocol (SQLite-backed queue now, swappable to
  Redis/NATS later)
- Abstract DB layer so each future service can share or have its own DB
- Package governance core as standalone module (`from swarm_governance import ...`)
- Build node registration system (`swarm_nodes` table) — each instance registers
  itself, agents, capabilities
- No process split yet — monolith still runs, but internal calls go through contracts

**Detailed sub-tasks:**

- [x] **A.4.1 — API Contract Definitions**
  - Document the API contract for each domain: Chat, Studio, Proposals, Vortex, Governance
  - Each contract: endpoints, request/response schemas, auth requirements
  - Store as JSON Schema or OpenAPI snippets in `docs/api/`
  - Blueprints must not cross-import from each other (enforce via lint/test)

- [x] **A.4.2 — Message Protocol (swarm_bus)**
  - `swarm_bus` table: (id, topic, payload_json, source_service, created_at, consumed_at)
  - Internal publish/subscribe within the process (function calls for now)
  - Topics: `proposal.created`, `proposal.status_changed`, `knowledge.new`,
    `agent.status_changed`
  - Each blueprint subscribes to relevant topics instead of direct cross-calls
  - Swappable: same interface works with Redis/NATS later by changing the transport

- [x] **A.4.3 — DB Layer Abstraction**
  - Each domain gets its own DB access module (already mostly done: utils/db/*.py)
  - Add connection factory that reads config: shared DB or per-service DB
  - Default: shared SQLite (current behaviour)
  - Future: each service can point to its own DB file

- [x] **A.4.4 — Governance Core as Standalone Module**
  - Package `utils/governance.py` + `utils/db/registry.py` + proposal engine as importable
  - Any future service (even on another machine) can `from swarm_governance import ...`
  - No Flask dependency in governance core — pure Python
  - Entry point for external services: validate, transition, enforce

- [x] **A.4.5 — Node Registration (Foundation)**
  - `swarm_nodes` table: (node_id, name, url, api_key_hash, role, agents_json,
    registered_at, last_seen)
  - `GET /api/node/info` — returns this node's identity, agents, capabilities
  - `POST /api/node/register` — a remote node registers itself (API key required)
  - No cross-node communication yet — just the registry scaffold

**Test Phase A.4:**
- [x] Lint: no cross-imports between blueprints (26 passed)
- [x] Unit: message bus publish → subscribe delivers payload (6 tests)
- [x] Unit: DB factory returns shared or per-service connection based on config (3 tests)
- [x] Unit: governance module works without Flask context (3 tests)
- [x] Integration: node registration stores and retrieves correctly (8 tests)
- [x] Full regression: 96 passed, 0 failed

---

### A.5 — Multi-Node Foundation (Weeks 6–7)

- Node-to-node discovery (REST + simple mDNS on local network)
- Shared proposal visibility across nodes (read-only at first)
- Cross-node agent roster and federated skill registry
- Basic node auth (API key per node, role-based: owner/contributor/viewer)

**Detailed sub-tasks:**

- [x] **A.5.1 — Node Discovery**
  - REST-based: each node exposes `GET /api/node/info`
  - mDNS for local network auto-discovery (optional, config-driven)
  - Heartbeat: each registered node pinged on interval, `last_seen` updated
  - Heartbeat daemon auto-started in terminal.py create_app()

- [x] **A.5.2 — Cross-Node Proposal Visibility**
  - `GET /api/node/proposals` — auth-protected view of local proposals for remote consumption
  - `GET /api/federation/proposals` — aggregates local + remote proposals with node badges
  - No cross-node proposal modification yet (read-only federation)

- [x] **A.5.3 — Federated Agent Roster + Skill Registry**
  - Each node publishes its agent list via `/api/node/info`
  - `GET /api/federation/roster` — aggregates local + remote agent rosters
  - Skill search federation deferred to Phase B

- [x] **A.5.4 — Node Authentication**
  - API key per node (hashed in swarm_nodes table)
  - Role-based: `owner` (full access), `contributor` (read + propose), `viewer` (read-only)
  - `require_node_api_key` decorator: checks X-Node-ID + X-Node-API-Key headers

**Test Phase A.5:**
- [x] Unit: node registration + heartbeat updates last_seen
- [x] Unit: API key validation accepts valid, rejects invalid
- [x] Integration: federation endpoints return local data correctly
- [x] Integration: remote proposals visible via federation API
- [ ] Manual: mDNS discovery finds a second node on the LAN (deferred)
- [x] Compile check + full regression: 112 passed, 1 skipped, 0 failed

---

### A.6 — Testing & Stability (Week 7)

- Full integration test suite for governance flows
- Health checks + circuit breakers on every boundary
- Install script / setup wizard for new nodes
- Config-driven (no hardcoded paths)

**Detailed sub-tasks:**

- [x] **A.6.1 — Integration Test Suite**
  - End-to-end test: proposal creation → governance gate → execution → trace → done
  - Skill trust test: all trust levels validated against all tiers
  - Cross-ref test: ticket → proposal → conversation links verified
  - **23 tests across 5 classes (TestProposalLifecycle, TestSkillTrust, TestCrossReferences, TestAgentCoordination, TestBusKnowledgeIntegration)**
  - **BUG FIX: governance.py post-commit side effects (knowledge+bus) were never committed — data silently lost on conn.close()**

- [x] **A.6.2 — Install Script / Setup Wizard**
  - `scripts/setup_node.py` — interactive setup for a new swarm node
  - Prompts: node name, API key, DB path, agents to enable
  - Generates config file, initialises DB, seeds default agents

- [x] **A.6.3 — Remove Hardcoded Paths**
  - Audit all Python files for `/home/seven/swarm` hardcodes
  - Replace with config-driven `SWARM_ROOT` environment variable
  - Default: auto-detect from script location
  - **Central module: utils/swarm_root.py + 12 infrastructure files updated**

**Test Phase A.6:**
- [x] Full test suite passes — **198 passed, 1 skipped, 0 failed**
- [x] Setup wizard creates a working node from scratch
- [x] System runs with custom SWARM_ROOT (not default path)
- [ ] All tiles functional after fresh install

---

## Communication Model Decision

For the "friends on local network" scenario, we start with **REST API**:

- Simple, works immediately, firewall-friendly
- Each swarm remains self-contained
- Cross-node features are opt-in API calls
- Message queue (Redis/NATS or SQLite-backed) added later when real-time
  coordination is needed

---

## Phase B — Research Assistant / Learning Lab (Weeks 8–12)

**Goal:** Give the swarm a structured research capability — human asks a question,
the swarm decomposes it, searches multiple sources, tracks evidence with citations,
synthesises findings, and archives lessons to shared knowledge. Multi-step
investigations can be paused and resumed.

**Builds on:** A.3 (swarm_knowledge + events), A.2 (agent coordination + trust),
A.1 (proposal governance + ALM gate).

**Existing assets:**
- Seeker agent (Tavily search, live web) — direct API, no skills_loop
- Scholar agent (Gemini 2.0, vision + reasoning) — uses skills_loop
- `SKILL search` (DuckDuckGo), `SKILL browse` (Playwright headless)
- `swarm_knowledge` table + event system (A.3)
- Orchestrator heartbeat with keyword-based dispatch routing
- Relay system with 4-hop budget for multi-agent chains

---

### B.1 — Research Session & Evidence Model (Week 8)

- New tables: `research_sessions`, `research_evidence`
- Session tracks: topic, depth, status, phases completed, linked proposal
- Evidence tracks: source URL, content snippet, confidence, agent, timestamp
- CRUD module: `utils/db/research.py`

**Detailed sub-tasks:**

- [ ] **B.1.1 — Research Tables**
  - `research_sessions` (id, topic, depth, status, phases_json, linked_proposal_id,
    requesting_agent, created_at, updated_at, summary)
  - `research_evidence` (id, session_id FK, source_url, source_type, title,
    snippet, confidence, collecting_agent, created_at)
  - Status values: `planning`, `searching`, `analysing`, `synthesising`, `done`, `paused`
  - Depth values: `quick` (1 source, 1 pass), `standard` (3 sources, 2 passes),
    `deep` (5+ sources, 3+ passes with cross-validation)

- [ ] **B.1.2 — Research DB Module**
  - `utils/db/research.py`: create_session, get_session, update_session,
    add_evidence, get_evidence_for_session, list_sessions
  - Reuses `get_connection()` from `utils/db/_connection.py`
  - Evidence deduplication by (session_id, source_url, snippet hash)

**Test Phase B.1:**
- [ ] Unit: create session, add evidence, retrieve by session
- [ ] Unit: evidence deduplication rejects same source+snippet
- [ ] Compile check: all new files pass `py_compile`

---

### B.2 — Research Workflow Engine (Weeks 8–9)

- Central orchestrator for multi-stage research
- Entry point: `run_research(topic, depth, requesting_agent)`
- Stages: decompose → search → fetch/browse → analyse → synthesise → archive
- Each stage updates session status and writes evidence

**Detailed sub-tasks:**

- [ ] **B.2.1 — Workflow Core**
  - New file: `fridays/research_workflow.py`
  - `run_research(topic, depth='standard', requesting_agent='user', conn=None)`
  - Creates research_session, runs stages sequentially
  - Each stage is a function: `_decompose()`, `_search()`, `_analyse()`, `_synthesise()`
  - Returns session_id + final summary

- [ ] **B.2.2 — Decompose Stage**
  - Break topic into 2–5 sub-questions depending on depth
  - Uses local agent (LLaMA or Qwen) for decomposition via chat dispatch
  - Stores sub-questions in session phases_json

- [ ] **B.2.3 — Search & Browse Stage**
  - For each sub-question: call Seeker (Tavily) for web results
  - Optionally: `SKILL browse` on top-N URLs for full content
  - Each result → `add_evidence()` with source_url, confidence, snippet
  - Depth controls parallelism: quick=1 query, standard=3, deep=5+

- [ ] **B.2.4 — Analyse & Synthesise Stage**
  - Feed collected evidence to Scholar (Gemini) for synthesis
  - Scholar produces: summary, key findings, confidence assessment, gaps
  - Cross-validate: if depth=deep, check contradictions across sources
  - Final synthesis stored in session.summary

- [ ] **B.2.5 — Archive Stage**
  - Auto-write findings to `swarm_knowledge` (category=`fact` or `lesson`)
  - Each knowledge entry linked to session via source_proposal_id
  - Emit `knowledge.new` bus event for other agents to consume

**Test Phase B.2:**
- [ ] Unit: decompose returns sub-questions
- [ ] Unit: search collects evidence records
- [ ] Integration: full workflow quick-depth completes end-to-end
- [ ] Integration: archive writes to swarm_knowledge

---

### B.3 — Research Skills & Agent Wiring (Week 9–10)

- New SKILL commands for agents to trigger and consume research
- Wire into skills.py REGISTRY with appropriate trust levels
- Agents can initiate, resume, and query research sessions

**Detailed sub-tasks:**

- [ ] **B.3.1 — Research Skills**
  - `SKILL research <topic>` — starts standard-depth research, returns session_id + summary
  - `SKILL deep_dive <topic>` — starts deep-depth research
  - `SKILL research_status <session_id>` — check progress of running session
  - `SKILL research_resume <session_id>` — resume a paused session
  - All registered in REGISTRY with trust_level=1 (any agent can research)

- [ ] **B.3.2 — Seeker Integration**
  - Wire Seeker into research workflow as the search provider
  - Seeker results auto-tagged with evidence metadata (URL, confidence, timestamp)
  - If Seeker unavailable: fallback to `SKILL search` (DuckDuckGo)

- [ ] **B.3.3 — Scholar Integration**
  - Scholar is the default analyser/synthesiser in the workflow
  - Receives evidence bundle → produces structured synthesis
  - If Scholar unavailable: fallback to local agent (Qwen/Mistral)

**Test Phase B.3:**
- [ ] Unit: SKILL research triggers workflow and returns summary
- [ ] Unit: SKILL deep_dive uses deep depth
- [ ] Unit: trust gate allows local agents to call research skills
- [ ] Integration: agent chat triggers research via SKILL command

---

### B.4 — Research API & Frontend (Week 10–11)

- REST endpoints for the frontend to display research sessions
- Research tile in Studio or dedicated panel
- Evidence viewer with source links and confidence indicators

**Detailed sub-tasks:**

- [ ] **B.4.1 — Research API Blueprint**
  - New file: `frontend/blueprints/research.py`
  - `POST /api/research/start` — {topic, depth} → starts session, returns session_id
  - `GET /api/research/sessions` — list all sessions (paginated)
  - `GET /api/research/<session_id>` — full session detail + evidence
  - `POST /api/research/<session_id>/resume` — resume paused session
  - `GET /api/research/<session_id>/evidence` — evidence list with filters

- [ ] **B.4.2 — Blueprint Registration**
  - Register research_bp in terminal.py
  - Protect behind ALM gate where appropriate
  - Add to API contract: `docs/api/research.json`

- [ ] **B.4.3 — Frontend Panel** (if Flutter/HTML frontend exists)
  - Research Sessions list view (topic, status, evidence count, date)
  - Session detail: summary, evidence cards with source links
  - Start Research form: topic input + depth selector
  - Evidence confidence colour coding (high=green, medium=amber, low=red)

**Test Phase B.4:**
- [ ] Unit: API returns correct session data
- [ ] Integration: POST /start creates session and begins workflow
- [ ] Integration: GET /sessions returns paginated list

---

### B.5 — Learning Cycle Closure (Week 11–12)

- Completed research auto-generates lessons learned
- Pattern detection across multiple research sessions
- Knowledge grows over time — agents get smarter

**Detailed sub-tasks:**

- [ ] **B.5.1 — Auto-Lessons from Research**
  - On research session → `done`: extract patterns and lessons
  - Write to swarm_knowledge with category=`lesson` and link to session
  - Include: what was searched, what was found, what was surprising, what gaps remain

- [ ] **B.5.2 — Cross-Session Pattern Detection**
  - When a new research session completes, compare findings with existing knowledge
  - If similar topic exists: update existing entry, note evolution
  - If contradicts existing knowledge: flag with category=`warning`
  - Simple similarity: keyword overlap + same category match

- [ ] **B.5.3 — Knowledge Feed for Agents**
  - Agents' system prompts get recent relevant knowledge injected
  - On chat dispatch: `_build_knowledge_broadcast_block()` (already exists from A.3.4)
  - Extend to include research findings relevant to the current conversation topic
  - Max 3 knowledge snippets injected per prompt (avoid bloat)

**Test Phase B.5:**
- [ ] Unit: completed research writes lessons to swarm_knowledge
- [ ] Unit: contradicting findings generate warning entries
- [ ] Integration: knowledge broadcast includes research findings

---

### B.6 — Testing & Stability (Week 12)

- Full integration test suite for research flows
- Regression across all A + B tests
- Stress test: concurrent research sessions

**Detailed sub-tasks:**

- [x] **B.6.1 — Research Integration Tests**
  - End-to-end: start session → search → analyse → synthesise → archive → verify knowledge
  - Pause/resume test: pause mid-search, resume, verify completion
  - Depth test: quick vs standard vs deep produce different evidence counts
  - Fallback test: Seeker down → DuckDuckGo fallback works
  - Learning cycle: lesson extraction, pattern detection, knowledge broadcast
  - 31 tests: 13 CRUD + 6 workflow + 7 skills + 5 learning cycle

- [x] **B.6.2 — Full Regression**
  - All A.x tests + all B.x tests pass
  - No cross-contamination between research sessions
  - Knowledge writes don't break existing governance flows

**Test Phase B.6:**
- [x] Full suite: 230 passed, 1 skipped, 0 failed
- [x] Compile check: all new/modified files clean
- [x] Service restart: no crash

---

## Phase C — Tool Builder Mode

Agents take ideas and build real tools, widgets, dashboards, or scripts through
the full governed ALM flow. Phase C adds structured scaffolding, a build
pipeline, auto-testing, and a tool registry so agent work products are
trackable, testable, and reusable.

**What exists today (inherited from A + B):**
- fs_write, fs_patch, fs_patch_lines (trust-gated file ops)
- fs_verify (Python AST / Node --check)
- alm_create_proposal → alm_self_approve → alm_complete (governed flow)
- Vortex checkpoints on in_progress & done transitions
- skills_loop (multi-pass agent execution with up to 6 SKILL calls per turn)
- Shell agent with whitelisting and sudo approval gate

**What Phase C adds:**
- `tool_builds` table — registry of everything agents have built
- Scaffold templates for common tool types (script, skill, widget, cron)
- Build pipeline engine — scaffold → generate → validate → test → register
- 5 new SKILL commands for agent-driven tool building
- Auto-test runner (discovers and runs tests for built tools)
- API + frontend visibility into all builds

---

### C.1 — Tool Registry & Scaffold Templates (Week 13)

- New table to track every tool an agent builds
- Template library for common tool types

**Detailed sub-tasks:**

- [x] **C.1.1 — tool_builds Table**
  - Add to `utils/db/_schema.py` (SCHEMA + migration)
  - Columns: id, proposal_id, tool_type, tool_name, description, entry_path,
    test_path, status (scaffolded/building/testing/passed/failed/registered),
    test_output, building_agent, language, created_at, updated_at
  - Index on (building_agent, status)

- [x] **C.1.2 — tool_builds CRUD Module**
  - New file: `utils/db/tools.py`
  - create_build, get_build, update_build, list_builds,
    list_builds_by_agent, get_build_by_proposal

- [x] **C.1.3 — Scaffold Templates**
  - New directory: `skills/templates/`
  - Templates: `python_script.py.tpl`, `python_skill.py.tpl`,
    `js_widget.js.tpl`, `shell_script.sh.tpl`, `cron_job.py.tpl`
  - Each template has {{PLACEHOLDERS}} for name, description, author, date
  - Matching test templates: `test_python_script.py.tpl`, etc.

**Test Phase C.1:**
- [x] Unit: CRUD create/get/update/list on tool_builds
- [x] Unit: scaffold templates parse without error
- [x] Unit: status transitions validated

---

### C.2 — Build Pipeline Engine (Week 13–14)

- Multi-stage orchestrator: scaffold → generate → validate → test → register
- Integrates with ALM: creates proposal, builds tool, marks done

**Detailed sub-tasks:**

- [x] **C.2.1 — Pipeline Orchestrator**
  - New file: `fridays/tool_builder.py`
  - `build_tool(tool_type, name, description, agent, *, spec=None, conn=None)`
    → creates proposal, scaffolds, creates build record, returns (build_id, entry_path)
  - `validate_tool(build_id, *, conn=None)` → runs fs_verify, returns (ok, errors)
  - `test_tool(build_id, *, conn=None)` → discovers + runs test file, returns (ok, output)
  - `register_tool(build_id, *, conn=None)` → marks passed, publishes to knowledge+bus

- [x] **C.2.2 — Scaffold Stage**
  - Read template, substitute placeholders, write to agent's sandpit
  - Create matching test file from test template
  - Record entry_path + test_path in tool_builds

- [x] **C.2.3 — Validate Stage**
  - Python: AST parse (same as fs_verify)
  - JavaScript: node --check
  - Shell: bash -n
  - Records validation result in tool_builds.test_output

- [x] **C.2.4 — Test Stage**
  - Python: `python3 -m pytest <test_path> --tb=short -q`
  - Shell: source file + run with `--help` or `--dry-run` flag
  - Timeout: 30 seconds, captures stdout+stderr
  - Updates build status to passed/failed

**Test Phase C.2:**
- [x] Unit: scaffold writes correct files from template
- [x] Unit: validate catches syntax errors
- [x] Unit: test stage runs pytest and captures output
- [x] Integration: full pipeline scaffold → validate → test → register

---

### C.3 — Tool Builder Skills (Week 14)

- 5 new SKILL commands for agents to build tools
- Wired into skills.py with handlers

**Detailed sub-tasks:**

- [x] **C.3.1 — Build Skill**
  - `SKILL build_tool <type> <name> <description>` — scaffold + ALM proposal
  - Types: script, skill, widget, cron, shell
  - Returns build_id and scaffolded file path

- [x] **C.3.2 — Tool Management Skills**
  - `SKILL tool_validate <build_id>` — run syntax validation
  - `SKILL tool_test <build_id>` — run tests
  - `SKILL tool_status <build_id>` — check build progress
  - `SKILL tool_list [agent]` — list builds (own or by agent)

- [x] **C.3.3 — Registry Entries**
  - All 5 skills added to REGISTRY with trust_level=1
  - Handlers in `_HANDLERS` dict

**Test Phase C.3:**
- [x] Unit: SKILL build_tool creates scaffold + DB record
- [x] Unit: SKILL tool_validate returns syntax check result
- [x] Unit: SKILL tool_test runs tests and records output
- [x] Unit: SKILL tool_list returns agent's builds

---

### C.4 — Tool Build API & Frontend (Week 14–15)

- API endpoints for Studio to display tool builds
- Frontend can trigger builds and view test results

**Detailed sub-tasks:**

- [x] **C.4.1 — Tool Build API Blueprint**
  - New file: `frontend/blueprints/tools.py`
  - `GET /api/tools/builds` — list builds with status/agent filter
  - `GET /api/tools/builds/<id>` — detail with test output
  - `POST /api/tools/builds` — start a build (type, name, description)
  - `POST /api/tools/builds/<id>/validate` — trigger validation
  - `POST /api/tools/builds/<id>/test` — trigger test run
  - `GET /api/tools/templates` — list available templates

- [x] **C.4.2 — Blueprint Registration**
  - Register tools_bp in terminal.py _BLUEPRINT_REGISTRY
  - API contract: `docs/api/tools.json`

**Test Phase C.4:**
- [x] Unit: API returns correct build data
- [x] Integration: POST /builds triggers pipeline
- [x] Integration: POST /<id>/test runs and returns results

---

### C.5 — Quality Gate Enhancement (Week 15)

- alm_complete validates tool builds before marking done
- Auto-test discovery for proposals with linked tool_builds

**Detailed sub-tasks:**

- [x] **C.5.1 — ALM Completion Gate**
  - Enhance alm_complete in skills.py: if proposal has linked tool_build,
    run validate + test before allowing done transition
  - Failed validation → reject with clear error message
  - Passed → attach test output to proposal notes

- [x] **C.5.2 — Knowledge Archival**
  - On tool registered: write to swarm_knowledge category=`tool`
  - Key: `tool:{type}:{name}`, content = description + entry_path + test status
  - Bus event: `tool.registered` with build_id + tool_name

**Test Phase C.5:**
- [x] Unit: alm_complete blocks when linked tool fails tests
- [x] Unit: alm_complete proceeds when linked tool passes
- [x] Integration: tool registration writes knowledge + bus event

---

### C.6 — Testing & Stability (Week 15)

- Full integration test suite for tool builder
- Regression across all A + B + C tests

**Detailed sub-tasks:**

- [x] **C.6.1 — Tool Builder Integration Tests**
  - CRUD: create/get/update/list builds
  - Pipeline: scaffold → validate → test → register
  - Skills: all 5 tool skills work correctly
  - Quality gate: alm_complete respects tool build status
  - Templates: each template scaffolds and validates

- [x] **C.6.2 — Full Regression**
  - All A.x tests + B.x tests + C.x tests pass
  - No regressions in governance, research, or knowledge flows

**Test Phase C.6:**
- [x] Full suite: all tests green (266 passed, 1 skipped)
- [x] Compile check: all new/modified files clean

---

## Phase D — Multi-Node Hardening & Desktop Readiness

Harden the multi-node foundation built in A.5, add cross-node event propagation,
federated skill routing, config management, and desktop packaging preparation.
The goal: any two machines running the swarm can discover, sync proposals, share
skills, and propagate events — with a path to desktop packaging via Tauri.

**What exists today (inherited from A + B + C):**
- Node discovery + heartbeat daemon (60s interval, REST-based)
- 8 node API endpoints including 2 federation aggregators
- Node auth framework (X-Node-ID / X-Node-API-Key headers)
- SQLite-backed swarm_bus (local-only, designed for Redis/NATS swap)
- 31 modular Flask blueprints (safe-failure model)
- swarm_nodes table with registration, roles, capabilities

**What Phase D adds:**
- Cross-node proposal sync with source_node tracking
- Federated skill registry with remote capability advertisement
- Bus event propagation across nodes via REST relay
- Node-level config management and environment templating
- Desktop packaging preparation (Tauri config, launcher, static assets)

---

### D.1 — Cross-Node Proposal Sync (Week 16)

- Add source_node tracking to proposals
- Fix federation auth forwarding bug
- Delta sync for proposal state changes

**Detailed sub-tasks:**

- [ ] **D.1.1 — Source Node Tracking**
  - Add `source_node` TEXT column to work_proposals table (schema + migration)
  - Default: local node_id. Set on create. Preserved on sync.
  - Update `create_proposal()` in governance.py to set source_node

- [ ] **D.1.2 — Fix Federation Auth Forwarding**
  - Fix `_fetch_remote_json()` in node.py to forward X-Node-ID / X-Node-API-Key
  - Use registered node credentials from swarm_nodes table
  - Add timeout and retry logic (3s timeout, 1 retry)

- [ ] **D.1.3 — Proposal Delta Sync**
  - New endpoint: `POST /api/node/sync/proposals` — accepts batch of proposals
  - Sync logic: if proposal_id exists locally, update if remote updated_at > local
  - Conflict resolution: last-writer-wins with source_node preserved
  - Bus event: `proposal.synced` on successful sync

**Test Phase D.1:**
- [ ] Unit: source_node set on create
- [ ] Unit: federation auth headers forwarded
- [ ] Unit: sync endpoint merges proposals correctly
- [ ] Unit: conflict resolution uses last-writer-wins

---

### D.2 — Federated Skill Registry (Week 16–17)

- Skills advertise their availability per-node
- Remote skill routing for cross-node execution

**Detailed sub-tasks:**

- [ ] **D.2.1 — Skill Capability Table**
  - New table: `node_skills` (node_id, skill_name, trust_level, available, last_seen)
  - Populated from local REGISTRY on startup
  - Refreshed on heartbeat response from remote nodes

- [ ] **D.2.2 — Skill Advertisement Endpoint**
  - `GET /api/node/skills` — returns this node's available skills
  - Included in heartbeat response payload
  - Heartbeat handler stores remote skills in node_skills table

- [ ] **D.2.3 — Remote Skill Lookup**
  - `find_skill_node(skill_name)` — checks local first, then node_skills
  - Returns (node_id, url) or None
  - Used by skills_loop when local skill unavailable

**Test Phase D.2:**
- [ ] Unit: node_skills populated on startup
- [ ] Unit: skill advertisement endpoint returns correct data
- [ ] Unit: remote skill lookup finds skills on other nodes
- [ ] Unit: heartbeat updates remote skill table

---

### D.3 — Bus Event Propagation (Week 17)

- Cross-node event relay via REST
- Topic-based filtering for efficient propagation

**Detailed sub-tasks:**

- [ ] **D.3.1 — Event Relay Endpoint**
  - `POST /api/node/events` — receives events from remote nodes
  - Auth: @require_node_api_key
  - Inserts into local swarm_bus with source_service=remote:{node_id}
  - Dedup: skip if event already exists (by topic+payload hash+timestamp window)

- [ ] **D.3.2 — Outbound Event Relay**
  - `relay_events(topics)` function in node_discovery.py
  - Called after heartbeat: POST unconsumed events to each reachable node
  - Topic filter: only relay proposal.*, knowledge.new, tool.registered
  - Mark relayed events with consumed_at to prevent re-relay

- [ ] **D.3.3 — Relay Configuration**
  - RELAY_TOPICS list (configurable via env var SWARM_RELAY_TOPICS)
  - RELAY_BATCH_SIZE = 50 (max events per relay call)
  - RELAY_MAX_AGE = 3600 (ignore events older than 1 hour)

**Test Phase D.3:**
- [ ] Unit: event relay endpoint inserts remote events
- [ ] Unit: dedup prevents duplicate events
- [ ] Unit: outbound relay sends to reachable nodes
- [ ] Unit: topic filtering works correctly

---

### D.4 — Config & Environment Management (Week 17–18)

- Node-level config overrides
- Environment validation and templating

**Detailed sub-tasks:**

- [ ] **D.4.1 — Config Validation**
  - New file: `utils/config_validator.py`
  - `validate_config()` — checks required env vars, DB connectivity,
    agent registry, API keys present
  - Returns (ok, errors[]) for preflight checks
  - Wired into startup sequence and `/_health` endpoint

- [ ] **D.4.2 — Node Config Override**
  - New table: `node_config` (key, value, node_id, updated_at)
  - `get_config(key, default)` — checks node_config first, then env, then default
  - `set_config(key, value)` — writes to node_config table
  - Startup loads node_config overrides into process env

- [ ] **D.4.3 — Environment Template**
  - New file: `scripts/generate_env.py`
  - Generates `.env.template` from required env vars
  - Documents each var with description and default value
  - Validates existing .env against template (missing/extra vars)

**Test Phase D.4:**
- [ ] Unit: config validation catches missing required vars
- [ ] Unit: node config overrides env vars correctly
- [ ] Unit: env template generation works

---

### D.5 — Desktop Packaging Prep (Week 18)

- Tauri configuration scaffolding
- Static asset bundling
- Launcher script for desktop mode

**Detailed sub-tasks:**

- [ ] **D.5.1 — Tauri Config Scaffold**
  - Create `desktop/` directory structure
  - `desktop/tauri.conf.json` — window config, app name, CSP headers
  - `desktop/src-tauri/Cargo.toml` — Rust scaffold
  - `desktop/README.md` — build instructions

- [ ] **D.5.2 — Desktop Launcher**
  - New file: `scripts/desktop_launcher.py`
  - Starts Flask backend on localhost:5050
  - Opens default browser or Tauri window
  - Handles graceful shutdown on window close
  - Supports --headless flag for server-only mode

- [ ] **D.5.3 — Static Asset Audit**
  - Verify all frontend routes return valid HTML/JSON
  - Ensure no hardcoded external URLs in frontend code
  - Create `frontend/static/manifest.json` listing all served assets

**Test Phase D.5:**
- [ ] Unit: launcher starts Flask and binds port
- [ ] Unit: Tauri config is valid JSON
- [ ] Unit: manifest.json lists all assets

---

### D.6 — Testing & Stability (Week 18)

- Full integration test suite for multi-node features
- Regression across all A + B + C + D tests

**Detailed sub-tasks:**

- [ ] **D.6.1 — Multi-Node Integration Tests**
  - Proposal sync: create → sync → verify on both sides
  - Skill federation: advertise → lookup → find remote
  - Event relay: publish → relay → receive on remote
  - Config: validate → override → verify
  - Federation auth: verify headers forwarded correctly

- [ ] **D.6.2 — Full Regression**
  - All A.x + B.x + C.x + D.x tests pass
  - No regressions in governance, research, tools, or node flows

**Test Phase D.6:**
- [ ] Full suite: all tests green
- [ ] Compile check: all new/modified files clean

---

## Phase E — Polish, Security & Final Analysis

Security hardening, performance tuning, observability, documentation
consolidation, and community readiness. Ends with a comprehensive
project analysis report.

**What Phase E delivers:**
- Input validation audit and rate limiting
- Concurrent heartbeat and DB query optimization
- Structured logging and metrics endpoint
- Consolidated API documentation and architecture diagram
- Community installer and onboarding guide
- Final project analysis with metrics, test coverage, and architecture review

---

### E.1 — Security Hardening (Week 19)

- Systematic input validation across all API endpoints
- Rate limiting for public endpoints
- CORS and auth strengthening

**Detailed sub-tasks:**

- [ ] **E.1.1 — Input Validation Audit**
  - Audit all POST/PUT endpoints for missing validation
  - Add request body size limits (1MB default)
  - Sanitize user inputs in proposal titles/descriptions
  - Validate all ID parameters (integer bounds, string length)

- [ ] **E.1.2 — Rate Limiting**
  - New middleware: `utils/rate_limiter.py`
  - Token bucket per IP, configurable via SWARM_RATE_LIMIT env var
  - Default: 60 requests/minute for API, 10/minute for auth endpoints
  - 429 response with Retry-After header

- [ ] **E.1.3 — Auth & CORS Hardening**
  - CORS: restrict to configured origins (default: localhost only)
  - Node API: strengthen hash comparison (constant-time via hmac.compare_digest)
  - Add X-Content-Type-Options, X-Frame-Options, X-XSS-Protection headers
  - Audit for any SQL injection vectors (parameterized queries check)

**Test Phase E.1:**
- [ ] Unit: oversized request bodies rejected
- [ ] Unit: rate limiter triggers at threshold
- [ ] Unit: CORS headers set correctly
- [ ] Unit: security headers present on all responses

---

### E.2 — Performance Tuning (Week 19–20)

- Concurrent heartbeat pings
- DB connection pooling
- Query optimization for hot paths

**Detailed sub-tasks:**

- [ ] **E.2.1 — Concurrent Heartbeat**
  - Replace sequential pings with ThreadPoolExecutor (max 5 workers)
  - Add exponential backoff for failed nodes (2s, 4s, 8s, max 60s)
  - Stale node cleanup: remove nodes not seen for 24 hours

- [ ] **E.2.2 — DB Query Optimization**
  - Add missing indexes on hot query paths
  - Index: work_proposals(status, agent)
  - Index: swarm_bus(consumed_at, topic)
  - Index: research_sessions(status)
  - EXPLAIN ANALYZE top 10 slowest queries

- [ ] **E.2.3 — Response Caching**
  - Cache federation/roster and federation/proposals (30s TTL)
  - Cache landscape.json (5min TTL, invalidate on knowledge write)
  - ETag support for GET endpoints

**Test Phase E.2:**
- [ ] Unit: concurrent heartbeat faster than sequential
- [ ] Unit: new indexes exist after migration
- [ ] Unit: cached responses return correct ETag

---

### E.3 — Observability (Week 20)

- Structured logging format
- Metrics endpoint for monitoring
- Health dashboard data

**Detailed sub-tasks:**

- [ ] **E.3.1 — Structured Logging**
  - New file: `utils/structured_logger.py`
  - JSON log format: timestamp, level, service, message, metadata
  - Correlation ID per request (X-Request-ID header)
  - Log rotation: 10MB max, 5 backups

- [ ] **E.3.2 — Metrics Endpoint**
  - `GET /api/metrics` — returns counters and gauges
  - Metrics: active_agents, proposals_by_status, bus_events_24h,
    research_sessions_active, tool_builds_by_status, node_count
  - Response time percentiles (p50, p95, p99) via middleware

- [ ] **E.3.3 — Health Dashboard Data**
  - Enhance `/_health` with detailed component status
  - Check: DB writable, heartbeat running, bus consuming, agents responding
  - Return degraded/healthy/unhealthy status per component

**Test Phase E.3:**
- [ ] Unit: structured logger outputs valid JSON
- [ ] Unit: metrics endpoint returns expected keys
- [ ] Unit: health check detects DB failure

---

### E.4 — Documentation Consolidation (Week 20–21)

- Unified API reference
- Architecture diagram
- Deployment guide

**Detailed sub-tasks:**

- [ ] **E.4.1 — API Reference**
  - Consolidate all docs/api/*.json into single reference
  - New file: `docs/API_REFERENCE.md` — human-readable with examples
  - Cover all 200+ routes grouped by domain

- [ ] **E.4.2 — Architecture Diagram**
  - Mermaid diagram in `docs/ARCHITECTURE_DIAGRAM.md`
  - Shows: agents → skills → governance → bus → federation → nodes
  - Layer diagram: frontend → blueprints → services → DB

- [ ] **E.4.3 — Deployment Guide**
  - New file: `docs/DEPLOYMENT_GUIDE.md`
  - Single-node setup (systemd services, env vars, DB init)
  - Multi-node setup (node registration, federation config)
  - Desktop mode (Tauri build, launcher)

**Test Phase E.4:**
- [ ] All API contracts valid JSON
- [ ] Mermaid diagram renders correctly
- [ ] Deployment guide covers all systemd services

---

### E.5 — Community Readiness (Week 21)

- Installer script
- README overhaul
- Example configurations

**Detailed sub-tasks:**

- [ ] **E.5.1 — Installer Script**
  - New file: `scripts/install.sh`
  - Checks Python 3.12+, creates venv, installs requirements
  - Runs setup_node.py, generates .env template
  - Creates systemd service files
  - Validates installation with health check

- [ ] **E.5.2 — README Overhaul**
  - Rewrite `docs/README.md` for external audience
  - Quick start guide (5 commands to running swarm)
  - Feature overview with screenshots/diagrams
  - Architecture overview (brief, links to full docs)
  - Contributing guide

- [ ] **E.5.3 — Example Configs**
  - `examples/single-node.env` — minimal single-node config
  - `examples/multi-node-primary.env` — primary node with federation
  - `examples/multi-node-secondary.env` — secondary node joining swarm

**Test Phase E.5:**
- [ ] Installer runs without errors on clean system
- [ ] README renders correctly (markdown lint)
- [ ] Example configs pass validation

---

### E.6 — Final Testing & Project Analysis (Week 21)

- Complete regression across all phases
- Comprehensive project analysis report

**Detailed sub-tasks:**

- [ ] **E.6.1 — Final Regression**
  - All A.x + B.x + C.x + D.x + E.x tests pass
  - Performance: test suite completes in < 120 seconds
  - Zero compile errors across all Python files

- [ ] **E.6.2 — Project Analysis Report**
  - New file: `docs/PROJECT_ANALYSIS.md`
  - Metrics: test count, code line count, file count, endpoint count
  - Architecture review: strengths, weaknesses, tech debt
  - Phase-by-phase summary with deliverables
  - Recommendations for future development
  - Risk assessment and mitigation strategies

**Test Phase E.6:**
- [ ] All tests green
- [ ] Project analysis complete and accurate

---

## Risks & Complications We Must Manage

- **Short-term breakage** during boundary introduction — monolith runs as fallback
- **Data migration** for registry, landscape, and knowledge tables — careful testing
- **Testing burden** increases — governance flows tested after every change
- **Temporary dual-path code** during A.4 (old monolith + new contracts)
- **Frontend impact** — some JS may need small updates for new service endpoints
- **Scope creep** — finish one sub-task before starting the next

---

## How We Will Work

**Workflow per sub-task (non-negotiable):**

1. **Read this plan** — check Progress Log for current state
2. **Build** — implement the sub-task
3. **Test** — run every test listed for that sub-task
4. **Log** — update Progress Log + Files Tracker in this document
5. **Commit** — `git add -A && git commit` + tag `vortex-aX.Y` only after tests pass
6. **Move on** — start the next sub-task

**Handling deviations during build:**

- **Quick fix** (< 5 min, obvious bug or missing import): fix immediately, log it
  in the Progress Log with `[DEVIATION]` prefix, include in the same commit
- **Non-trivial issue** (new feature, refactor, or risk of side effects): do NOT
  fix inline. Add to the Follow-Up Activities section at the bottom of this plan.
  Continue with the current sub-task.

**Rules:**

- One sub-task at a time
- Clear testing steps after each change
- If it starts feeling bad, we stop immediately
- You stay in full control — this is your lab
- Targeted edits for modifications, whole-file only for new files or complete rewrites
- Never commit broken code — if tests fail, fix before committing

---

## Progress Log

Update this section as work proceeds.

```
DATE       | TASK                  | STATUS     | NOTES
-----------|-----------------------|------------|------
2026-04-15 | Plan v1.1 created     | Completed  | Multi-node vision incorporated
2026-04-15 | A.1.1 Singleton       | Completed  | utils/governance.py: transition_proposal() + state machine + optimistic lock + audit log. 10 call sites wired.
2026-04-15 | A.1.2 ALM Gate        | Completed  | Removed _is_time_wizard_active() bypass. Gate always enforced. Accepts approved+in_progress.
2026-04-15 | A.1.3 Vortex Git      | Completed  | create_workflow_checkpoint now does git add+commit+tag. restore uses git revert (fallback to reset). Auto-checkpoint on →in_progress and →done.
2026-04-15 | A.1.4 Auto-Trace      | Completed  | Every transition writes to conv_timeline via timeline_append. job_id=gov-{proposal_id}.
2026-04-15 | A.1 Tests             | Completed  | 12/12 pytest pass. All 11 files py_compile clean.
2026-04-15 | A.2.1 Trust Gate      | Completed  | _trust_gate() in skills.call(). TIER_MAX_TRUST map. Override via user_skill_permissions.
2026-04-15 | A.2.2 Agent Status    | Completed  | GET /api/agents/status endpoint. SKILL agent_status handler. Derives from chat_jobs+CB+registry.
2026-04-15 | A.2.3 Self-Coord      | Completed  | utils/agent_coordination.py: check_and_reroute, claim_pending_proposal. Wired into chat.py dispatch.
2026-04-15 | A.2 Tests             | Completed  | 20/20 pytest pass. 6 files py_compile clean. Regression: 32/32 total.
2026-04-15 | A.3.1 Knowledge Table | Completed  | swarm_knowledge + swarm_events tables. utils/db/knowledge.py CRUD + events. 4 new skills.
2026-04-15 | A.3.2 Auto-Publish    | Completed  | _auto_publish_knowledge() in governance.py. Fires on →done. Uses caller conn (no lock).
2026-04-15 | A.3.3 Living Landscape| Completed  | scripts/generate_landscape_json.py. JSON index (547 entries). Housekeeping refresh wired.
2026-04-15 | A.3.4 Memory Broadcast| Completed  | Events emitted on knowledge write. _build_knowledge_broadcast_block() in chat.py prompts.
2026-04-15 | A.3 Tests             | Completed  | 17/17 pytest pass. 9 files py_compile clean. Regression: 49/49 total.
2026-04-16 | A.4.1 API Contracts   | Completed  | 5 JSON contracts in docs/api/ (chat, proposals, governance, vortex, studio). Cross-import lint test: 26 passed.
2026-04-16 | A.4.2 swarm_bus       | Completed  | utils/swarm_bus.py: publish/subscribe + SQLite persistence. swarm_bus table + indexes. Governance wired via _bus_broadcast().
2026-04-16 | A.4.3 DB Abstraction  | Completed  | get_service_connection(service) in _connection.py. Reads SWARM_DB_{SERVICE}_PATH env. Default: shared DB.
2026-04-16 | A.4.4 Governance Pkg  | Completed  | swarm_governance.py re-exports all public governance API. No Flask dependency.
2026-04-16 | A.4.5 Node Registry   | Completed  | swarm_nodes table. utils/db/nodes.py CRUD. frontend/blueprints/node.py: /api/node/info, /register, /list.
2026-04-16 | A.4 Tests             | Completed  | 20/20 A.4 tests + 26 lint tests. Regression: 96 passed, 0 failed.
2026-04-16 | A.5.1 Node Discovery  | Completed  | utils/node_discovery.py: ping_node, run_heartbeat_once, start/stop_heartbeat. Daemon in terminal.py.
2026-04-16 | A.5.2 Cross-Node Props| Completed  | GET /api/node/proposals (auth), GET /api/federation/proposals (aggregated + node badges).
2026-04-16 | A.5.3 Federated Roster| Completed  | GET /api/federation/roster — aggregates local + remote agent lists.
2026-04-16 | A.5.4 Node Auth       | Completed  | require_node_api_key decorator. X-Node-ID + X-Node-API-Key header validation.
2026-04-16 | A.5 Tests             | Completed  | 16/16 A.5 tests. Full regression: 112 passed, 1 skipped, 0 failed.
2026-04-16 | A.6.1 Integration     | Completed  | 23 tests across 5 classes. BUG FIX: governance post-commit side effects lost. 
2026-04-16 | A.6.2 Setup Wizard    | Completed  | scripts/setup_node.py — interactive/auto mode, DB init, agent seeding, config gen.
2026-04-16 | A.6.3 Hardcoded Paths | Completed  | utils/swarm_root.py + 12 infrastructure files updated. SWARM_ROOT env var + auto-detect.
2026-04-16 | A.6 Tests             | Completed  | Full regression: 198 passed, 1 skipped, 0 failed.
2026-04-16 | B.1 Evidence Model    | Completed  | research_sessions + research_evidence tables. utils/db/research.py CRUD + dedup.
2026-04-16 | B.2 Workflow Engine   | Completed  | fridays/research_workflow.py: 5-stage orchestrator. Tavily→DDG fallback. Scholar→structured fallback.
2026-04-16 | B.3 Research Skills   | Completed  | 4 skills: research, deep_dive, research_status, research_resume. Handlers in skills.py.
2026-04-16 | B.4 Research API      | Completed  | 5 endpoints in frontend/blueprints/research.py. Async for standard/deep. API contract.
2026-04-16 | B.5 Learning Cycle    | Completed  | Lesson extraction (Qwen+fallback), pattern detection, knowledge broadcast enhancement.
2026-04-16 | B.6 Tests + Commit    | Completed  | 31 research tests + full regression: 230 passed, 1 skipped, 0 failed.
2026-04-16 | C.1 Tool Registry     | Completed  | tool_builds table + CRUD (utils/db/tools.py) + 7 scaffold templates.
2026-04-16 | C.2 Build Pipeline    | Completed  | fridays/tool_builder.py: scaffold→validate→test→register. AST/node/bash validators.
2026-04-16 | C.3 Tool Skills       | Completed  | 5 skills: build_tool, tool_validate, tool_test, tool_status, tool_list.
2026-04-16 | C.4 Tool API          | Completed  | 7 endpoints in frontend/blueprints/tools.py. Blueprint registered. API contract.
2026-04-16 | C.5 Quality Gate      | Completed  | alm_complete: linked tool_build validate+test gate. BLOCKED on failure.
2026-04-16 | C.6 Tests + Commit    | Completed  | 35 tool tests + full regression: 266 passed, 1 skipped, 0 failed.
           |                       |            |
```

---

## Files Modified / Created Tracker

Track every file touched for audit and rollback.

```
FILE                                      | ACTION   | TASK   | DATE
------------------------------------------|----------|--------|-----
docs/PHASE_4.0_DIAMOND_LAYER.md           | Created  | Plan   | 2026-04-15
utils/governance.py                       | Created  | A.1.1  | 2026-04-15
utils/db/_schema.py                       | Modified | A.1.1  | 2026-04-15
frontend/blueprints/proposals.py          | Modified | A.1.1  | 2026-04-15
frontend/services.py                      | Modified | A.1.1+2| 2026-04-15
utils/proposal_review.py                  | Modified | A.1.1  | 2026-04-15
core/pipeline/queue_manager.py            | Modified | A.1.1  | 2026-04-15
utils/change_logger.py                    | Modified | A.1.1  | 2026-04-15
core/time_machine.py                      | Modified | A.1.1+3| 2026-04-15
tests/test_governance.py                  | Created  | A.1.1  | 2026-04-15
utils/agent_coordination.py               | Created  | A.2.3  | 2026-04-15
fridays/skills.py                         | Modified | A.2.1+2| 2026-04-15
frontend/blueprints/agents.py             | Modified | A.2.2  | 2026-04-15
frontend/blueprints/agent_api.py          | Modified | A.2.3  | 2026-04-15
frontend/blueprints/chat.py               | Modified | A.2.3  | 2026-04-15
tests/test_skill_trust.py                 | Created  | A.2    | 2026-04-15
utils/db/_schema.py                       | Modified | A.3.1  | 2026-04-15
utils/db/knowledge.py                     | Created  | A.3.1  | 2026-04-15
fridays/skills.py                         | Modified | A.3.1  | 2026-04-15
utils/governance.py                       | Modified | A.3.2  | 2026-04-15
scripts/generate_landscape_json.py        | Created  | A.3.3  | 2026-04-15
lib/system/housekeeping.py                | Modified | A.3.3  | 2026-04-15
frontend/blueprints/chat.py               | Modified | A.3.4  | 2026-04-15
tests/test_shared_knowledge.py            | Created  | A.3    | 2026-04-15
docs/api/chat.json                        | Created  | A.4.1  | 2026-04-16
docs/api/proposals.json                   | Created  | A.4.1  | 2026-04-16
docs/api/governance.json                  | Created  | A.4.1  | 2026-04-16
docs/api/vortex.json                      | Created  | A.4.1  | 2026-04-16
docs/api/studio.json                      | Created  | A.4.1  | 2026-04-16
tests/test_no_cross_imports.py            | Created  | A.4.1  | 2026-04-16
utils/swarm_bus.py                        | Created  | A.4.2  | 2026-04-16
utils/db/_schema.py                       | Modified | A.4.2+5| 2026-04-16
utils/governance.py                       | Modified | A.4.2  | 2026-04-16
utils/db/_connection.py                   | Modified | A.4.3  | 2026-04-16
swarm_governance.py                       | Created  | A.4.4  | 2026-04-16
utils/db/nodes.py                         | Created  | A.4.5  | 2026-04-16
frontend/blueprints/node.py              | Created  | A.4.5  | 2026-04-16
frontend/terminal.py                      | Modified | A.4.5  | 2026-04-16
tests/test_service_boundaries.py          | Created  | A.4    | 2026-04-16
utils/node_discovery.py                   | Created  | A.5.1  | 2026-04-16
frontend/blueprints/node.py               | Modified | A.5.2-4| 2026-04-16
frontend/terminal.py                      | Modified | A.5.1  | 2026-04-16
tests/test_multi_node.py                  | Created  | A.5    | 2026-04-16
tests/test_integration.py                 | Created  | A.6.1  | 2026-04-16
utils/governance.py                       | Modified | A.6.1  | 2026-04-16
scripts/setup_node.py                     | Created  | A.6.2  | 2026-04-16
utils/swarm_root.py                       | Created  | A.6.3  | 2026-04-16
utils/db/_connection.py                   | Modified | A.6.3  | 2026-04-16
core/time_machine.py                      | Modified | A.6.3  | 2026-04-16
utils/git_commit_logger.py                | Modified | A.6.3  | 2026-04-16
frontend/blueprints/git.py               | Modified | A.6.3  | 2026-04-16
utils/vs_tools.py                         | Modified | A.6.3  | 2026-04-16
frontend/blueprints/exec_bp.py           | Modified | A.6.3  | 2026-04-16
frontend/blueprints/proposals.py          | Modified | A.6.3  | 2026-04-16
fridays/file_agent.py                     | Modified | A.6.3  | 2026-04-16
fridays/skills.py                         | Modified | A.6.3  | 2026-04-16
frontend/blueprints/workspace.py          | Modified | A.6.3  | 2026-04-16
frontend/blueprints/shell.py             | Modified | A.6.3  | 2026-04-16
fridays/shell_agent.py                    | Modified | A.6.3  | 2026-04-16
lib/system/logging_bridge.py              | Modified | A.6.3  | 2026-04-16
utils/db/_schema.py                       | Modified | B.1.1  | 2026-04-16
utils/db/research.py                      | Created  | B.1.2  | 2026-04-16
fridays/research_workflow.py               | Created  | B.2+5  | 2026-04-16
fridays/skills.py                         | Modified | B.3    | 2026-04-16
frontend/blueprints/research.py           | Created  | B.4    | 2026-04-16
frontend/terminal.py                      | Modified | B.4    | 2026-04-16
docs/api/research.json                    | Created  | B.4    | 2026-04-16
frontend/blueprints/chat.py               | Modified | B.5    | 2026-04-16
tests/test_research.py                    | Created  | B.6    | 2026-04-16
utils/db/_schema.py                       | Modified | C.1.1  | 2026-04-16
utils/db/tools.py                         | Created  | C.1.2  | 2026-04-16
skills/templates/python_script.py.tpl     | Created  | C.1.3  | 2026-04-16
skills/templates/test_python_script.py.tpl| Created  | C.1.3  | 2026-04-16
skills/templates/python_skill.py.tpl      | Created  | C.1.3  | 2026-04-16
skills/templates/test_python_skill.py.tpl | Created  | C.1.3  | 2026-04-16
skills/templates/js_widget.js.tpl         | Created  | C.1.3  | 2026-04-16
skills/templates/shell_script.sh.tpl      | Created  | C.1.3  | 2026-04-16
skills/templates/cron_job.py.tpl          | Created  | C.1.3  | 2026-04-16
skills/templates/test_cron_job.py.tpl     | Created  | C.1.3  | 2026-04-16
fridays/tool_builder.py                   | Created  | C.2    | 2026-04-16
fridays/skills.py                         | Modified | C.3+5  | 2026-04-16
frontend/blueprints/tools.py              | Created  | C.4.1  | 2026-04-16
frontend/terminal.py                      | Modified | C.4.2  | 2026-04-16
docs/api/tools.json                       | Created  | C.4.2  | 2026-04-16
tests/test_tools.py                       | Created  | C.6    | 2026-04-16
                                          |          |        |
```

---

## Decisions Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | REST-first for multi-node communication | Simple, works now, firewall-friendly. Queue later. | 2026-04-15 |
| 2 | Governance core built with service boundaries | Distribution-ready from day one, not bolted on later. | 2026-04-15 |
| 3 | Proposal singleton per-agent (not global) | Agents work in parallel, but each only one proposal at a time. | 2026-04-15 |
| 4 | SQLite-backed message bus (swappable) | Zero new dependencies now. Same interface works with Redis/NATS later. | 2026-04-15 |
| 5 | Trust enforcement: tier-based + overrides | Simple defaults, granular exceptions via user_skill_permissions. | 2026-04-15 |
| 6 | Targeted edits over whole-file replacement | Safer for large files (1000+ lines). Whole-file only for new files. | 2026-04-15 |

---

## Rollback Plan

1. Every sub-task gets a git tag: `vortex-a1.1`, `vortex-a1.2`, etc.
2. Rollback: `git revert --no-commit {tag}..HEAD`
3. Monolith fallback remains available during transition
4. New tables are additive (no destructive changes to existing tables)

---

## Follow-Up Activities

Items discovered during build that are out of scope for the current sub-task.
Reviewed at the end of each phase section (A.1, A.2, etc.) and either scheduled
into a future sub-task or rejected.

```
FOUND DURING | DESCRIPTION                                      | PRIORITY | RESOLVED IN
-------------|--------------------------------------------------|----------|------------
             |                                                  |          |
```
