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

- [ ] **A.1.1 — Proposal Singleton Enforcement**
  - Max 1 `in_progress` proposal per agent at any time
  - `transition_proposal(proposal_id, new_status, agent)` — central state machine
  - Validates: current → new status is legal, agent owns it, no collision
  - Optimistic locking: check-and-set with row version or timestamp
  - Location: new file `utils/governance.py`

- [ ] **A.1.2 — Mandatory ALM Gate**
  - Remove the conditional check around `_alm_gate_or_response()` in services.py
  - ALM gate always enforced regardless of Time Wizard state
  - Duck sanity check called before any execution begins
  - If Duck is unavailable, proposal blocks (does not silently proceed)

- [ ] **A.1.3 — Vortex Real Git Integration**
  - `create_checkpoint()` → `git add -A && git commit -m "..." && git tag vortex-{id}`
  - `restore_checkpoint()` → `git revert --no-commit {tag}..HEAD && git commit`
  - Auto-checkpoint on proposal status → `in_progress` and → `done`
  - Checkpoint metadata stored in `time_checkpoints` table (already exists)
  - Handle dirty working tree gracefully (stash/warn)

- [ ] **A.1.4 — Auto-Trace on Proposal Lifecycle**
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

- [ ] **A.2.1 — Trust Level Enforcement**
  - In `skills.call()`: look up agent's tier/role from registry
  - Compare against skill's `trust_level` in REGISTRY
  - Block and log if agent tier < required trust_level
  - Mapping: tier `local` → max trust 1, tier `paid` → max trust 2, `ghost` → trust 4
  - Configurable override via `user_skill_permissions` table

- [ ] **A.2.2 — Agent Status API**
  - `GET /api/agents/status` → per-agent: name, status (idle/busy/down/disabled),
    active_jobs, circuit_breaker_state, last_seen
  - Status derived from: chat_jobs (running = busy), circuit breaker (open = down),
    registry (enabled = disabled)
  - `SKILL agent_status [agent_name]` — agents can query this themselves

- [ ] **A.2.3 — Agent Self-Coordination**
  - On relay handoff: agent checks target availability via agent_status before dispatch
  - If target busy/down: auto-reroute to next-best agent by role match from registry
  - Idle agents can claim queued proposals that match their role/capabilities
  - Claim mechanism: atomic UPDATE with WHERE status='pending' AND agent IS NULL

**Test Phase A.2:**
- [ ] Unit: local agent blocked from trust_level 2+ skill
- [ ] Unit: ghost can call any skill
- [ ] Unit: user_skill_permissions override grants access
- [ ] Integration: /api/agents/status returns correct busy/idle for running jobs
- [ ] Integration: relay to down agent auto-reroutes to alternative
- [ ] Integration: idle agent claims pending proposal
- [ ] Compile check + service restart

---

### A.3 — Shared Memory + Living Landscape (Weeks 3–4)

- Central `swarm_knowledge` table (any agent reads, governed writes only)
- Auto-publish key learnings from every completed proposal
- Living `system_landscape.md` + JSON index (files, buttons, fields, SAP mappings, workflows)
- `SKILL search_landscape` and `SKILL update_landscape`
- Housekeeping agents (Llama + Gemma3) can maintain the map

**Detailed sub-tasks:**

- [ ] **A.3.1 — Shared Knowledge Table**
  - New table: `swarm_knowledge` (id, key, content, source_agent, source_proposal_id,
    category, importance, created_at, updated_at)
  - Categories: `lesson`, `decision`, `fact`, `pattern`, `warning`
  - Any agent can read. Writes governed: only from completed proposal context or ghost
  - `SKILL knowledge_write <category> <content>` — governed
  - `SKILL knowledge_search <query>` — open (extends existing memory_search)

- [ ] **A.3.2 — Auto-Publish from Proposals**
  - When proposal status → `done`: extract key learnings from the proposal's trace
  - Agent that completed the proposal writes a summary to swarm_knowledge
  - Summary includes: what changed, why, what was learned, what to avoid
  - Triggered automatically in the proposal transition function (A.1.1)

- [ ] **A.3.3 — Living Landscape**
  - Extend system index generator to track: buttons, fields, workflows, SAP mappings
  - JSON version alongside MD (machine-queryable)
  - `SKILL search_landscape <query>` — fast grep over the JSON index
  - `SKILL update_landscape <path> <description>` — governed update
  - Housekeeping agents (Llama, Gemma3) scheduled to refresh quarterly

- [ ] **A.3.4 — Memory Broadcast**
  - When swarm_knowledge gets a new entry: emit a lightweight event
  - Other agents see "new knowledge available" in their next prompt context
  - Implementation: `swarm_events` table (event_type, payload, created_at, consumed_by)
  - No real-time push needed yet — poll on next agent invocation

**Test Phase A.3:**
- [ ] Unit: agent can read swarm_knowledge, write blocked outside proposal context
- [ ] Unit: ghost can write directly
- [ ] Integration: complete a proposal → swarm_knowledge entry auto-created
- [ ] Integration: SKILL search_landscape finds known file/button/field
- [ ] Integration: new knowledge entry creates event, another agent sees it
- [ ] Manual: run landscape generator, verify JSON matches MD
- [ ] Compile check + service restart

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

- [ ] **A.4.1 — API Contract Definitions**
  - Document the API contract for each domain: Chat, Studio, Proposals, Vortex, Governance
  - Each contract: endpoints, request/response schemas, auth requirements
  - Store as JSON Schema or OpenAPI snippets in `docs/api/`
  - Blueprints must not cross-import from each other (enforce via lint/test)

- [ ] **A.4.2 — Message Protocol (swarm_bus)**
  - `swarm_bus` table: (id, topic, payload_json, source_service, created_at, consumed_at)
  - Internal publish/subscribe within the process (function calls for now)
  - Topics: `proposal.created`, `proposal.status_changed`, `knowledge.new`,
    `agent.status_changed`
  - Each blueprint subscribes to relevant topics instead of direct cross-calls
  - Swappable: same interface works with Redis/NATS later by changing the transport

- [ ] **A.4.3 — DB Layer Abstraction**
  - Each domain gets its own DB access module (already mostly done: utils/db/*.py)
  - Add connection factory that reads config: shared DB or per-service DB
  - Default: shared SQLite (current behaviour)
  - Future: each service can point to its own DB file

- [ ] **A.4.4 — Governance Core as Standalone Module**
  - Package `utils/governance.py` + `utils/db/registry.py` + proposal engine as importable
  - Any future service (even on another machine) can `from swarm_governance import ...`
  - No Flask dependency in governance core — pure Python
  - Entry point for external services: validate, transition, enforce

- [ ] **A.4.5 — Node Registration (Foundation)**
  - `swarm_nodes` table: (node_id, name, url, api_key_hash, role, agents_json,
    registered_at, last_seen)
  - `GET /api/node/info` — returns this node's identity, agents, capabilities
  - `POST /api/node/register` — a remote node registers itself (API key required)
  - No cross-node communication yet — just the registry scaffold

**Test Phase A.4:**
- [ ] Lint: no cross-imports between blueprints
- [ ] Unit: message bus publish → subscribe delivers payload
- [ ] Unit: DB factory returns shared or per-service connection based on config
- [ ] Unit: governance module works without Flask context
- [ ] Integration: node registration stores and retrieves correctly
- [ ] Manual: verify all existing functionality unchanged after refactor
- [ ] Full compile check + service restart + smoke test all major tiles

---

### A.5 — Multi-Node Foundation (Weeks 6–7)

- Node-to-node discovery (REST + simple mDNS on local network)
- Shared proposal visibility across nodes (read-only at first)
- Cross-node agent roster and federated skill registry
- Basic node auth (API key per node, role-based: owner/contributor/viewer)

**Detailed sub-tasks:**

- [ ] **A.5.1 — Node Discovery**
  - REST-based: each node exposes `GET /api/node/info`
  - mDNS for local network auto-discovery (optional, config-driven)
  - Heartbeat: each registered node pinged on interval, `last_seen` updated

- [ ] **A.5.2 — Cross-Node Proposal Visibility**
  - `GET /api/node/<node_id>/proposals` — read-only view of remote proposals
  - Local UI shows proposals from all connected nodes with a node badge
  - No cross-node proposal modification yet (read-only federation)

- [ ] **A.5.3 — Federated Agent Roster + Skill Registry**
  - Each node publishes its agent list + skill list via `/api/node/info`
  - Central registry aggregates: "my swarm has Gemma/LLaMA, yours has Mistral/Qwen"
  - Skill search includes remote skills (flagged as remote in results)

- [ ] **A.5.4 — Node Authentication**
  - API key per node (hashed in swarm_nodes table)
  - Role-based: `owner` (full access), `contributor` (read + propose), `viewer` (read-only)
  - All cross-node endpoints require valid API key header

**Test Phase A.5:**
- [ ] Unit: node registration + heartbeat updates last_seen
- [ ] Unit: API key validation accepts valid, rejects invalid
- [ ] Integration: two nodes register with each other, rosters visible
- [ ] Integration: remote proposals visible in local UI
- [ ] Manual: mDNS discovery finds a second node on the LAN
- [ ] Compile check + service restart

---

### A.6 — Testing & Stability (Week 7)

- Full integration test suite for governance flows
- Health checks + circuit breakers on every boundary
- Install script / setup wizard for new nodes
- Config-driven (no hardcoded paths)

**Detailed sub-tasks:**

- [ ] **A.6.1 — Integration Test Suite**
  - End-to-end test: proposal creation → governance gate → execution → trace → done
  - Skill trust test: all trust levels validated against all tiers
  - Cross-ref test: ticket → proposal → conversation links verified

- [ ] **A.6.2 — Install Script / Setup Wizard**
  - `scripts/setup_node.py` — interactive setup for a new swarm node
  - Prompts: node name, API key, DB path, agents to enable
  - Generates config file, initialises DB, seeds default agents

- [ ] **A.6.3 — Remove Hardcoded Paths**
  - Audit all Python files for `/home/seven/swarm` hardcodes
  - Replace with config-driven `SWARM_ROOT` environment variable
  - Default: auto-detect from script location

**Test Phase A.6:**
- [ ] Full test suite passes
- [ ] Setup wizard creates a working node from scratch
- [ ] System runs with custom SWARM_ROOT (not default path)
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

## Future Phases (Context Only — Not Planned in Detail Yet)

**Phase B — Research Assistant / Learning Lab (after A)**
Shared memory active across the swarm. Agents + humans collaborate on proposals.
System learns from every completed project (auto-publish to swarm_knowledge).
Research mode: human asks question → swarm maps, researches, proposes, builds.

**Phase C — Tool Builder Mode (after B)**
Agents take ideas and build real tools, widgets, dashboards, or scripts through
the full governed ALM flow.

**Phase D — Multi-Node & Desktop Readiness (after C)**
Full node discovery and cross-node proposal sharing. Federated agent roster and
skill registry. Desktop packaging (Tauri) with each major tile as self-contained
module.

**Phase E — Polish & Scale (ongoing)**
Security hardening, performance tuning, community installers, swarm-to-swarm
federation at scale.

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
           |                       |            |
```

---

## Files Modified / Created Tracker

Track every file touched for audit and rollback.

```
FILE                                      | ACTION   | TASK   | DATE
------------------------------------------|----------|--------|-----
docs/PHASE_4.0_DIAMOND_LAYER.md           | Created  | Plan   | 2026-04-15
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
