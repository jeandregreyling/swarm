# SWARM PROJECT — Living Project Memory

> **How to use this file:** Start every session with *"look at the vibe coding project memory and see where we are at"*.  
> This is the single source of truth for project status, decisions, and session history.  
> Read **§1 STATUS** first. Read deeper only when needed.  
> Agents: this file is in the Library — consult it before proposing work to understand what's been done and what's planned.

**Owner:** Seven  
**Primary Builder:** Agent 12 (Claude / Copilot)  
**Created:** 16 April 2026  
**Last Updated:** 16 April 2026  

---

## §1 — CURRENT STATUS

| Field | Value |
|-------|-------|
| **Active Phase** | Phase 4.0 — Diamond Layer (Sub-task A, not yet started) |
| **Last Session** | 16 April 2026 — Sundial fix, SVG icons, V-RAM/GPU metrics, project memory creation |
| **Next Action** | "Fridays as a vibe" concept → then Diamond Layer A.1 |
| **Test Baseline** | 398 passed, 1 skipped |
| **Environments** | PROD (master), UAT, DEV — all synced as of 16 April 2026 |
| **Blockers** | None |

### What's Hot Right Now
- Sundial rendering on home screen: **working** (was cache issue)
- SVG icons: **all converted** from emoji to themed stroke icons
- Metrics: CPU, RAM, V-RAM (128GB SSD swap), GPU (N/A until hardware), Temp, Disk, Members, Gov
- Project tracking: **this document** — replaces loose doc sprawl

---

## §2 — PHASE MAP

### Completed Phases

| Phase | Name | Completed | Key Deliverable |
|-------|------|-----------|-----------------|
| V1 | Initial Build | March 2026 | Flask monolith, 12 agents, SQLite, terminal UI |
| V2 | Refinement | 28 Mar 2026 | Bug audit (26 bugs fixed), BRK-002 timeout fix, world clocks |
| V3 | Stabilisation | 30 Mar 2026 | ALM governance, Time Wizard, 3-stage workflow, proposals |
| P1 | Fix What's Broken | 15 Apr 2026 | Tickets tile fix, Vortex→Git wiring, relay limit default 2, parallel toggle |
| P2 | Agent Registry | 15 Apr 2026 | 15 hardcoded dicts → DB, cached registry with 11 accessors, invalidation |
| P3a | Local Agent Skills | 15 Apr 2026 | Gemma/Qwen/Eight routed via .chat()→skills_loop (not orchestrator) |
| P3b | Trace Troubleshooter | 15 Apr 2026 | job_id on timeline, trace API, Trace tile + frontend |
| P4 | Fault Isolation | 15 Apr 2026 | Circuit breaker (3-state), health probe, stuck-job sweep, error boundaries |
| P5 | Lift-and-Shift | 15 Apr 2026 | Model discovery, hot-swap, import/export, system index, cross-referencing |
| Diamond A (prep) | Frontend Polish | 16 Apr 2026 | Sundial pulse, SVG icons, V-RAM/GPU metrics, keyboard shortcuts |

### Active Phase

| Phase | Name | Status | Target |
|-------|------|--------|--------|
| **4.0-A** | Diamond Layer — Governance Core | NOT STARTED | Weeks 1–7 |

Sub-tasks (see `docs/PHASE_4.0_DIAMOND_LAYER.md` for full spec):

| Sub-task | Description | Status |
|----------|-------------|--------|
| A.1 | Proposal engine + governance core (singleton, ALM gate, Vortex git, auto-trace) | 🔲 |
| A.2 | Skill trust enforcement + agent status/awareness API | 🔲 |
| A.3 | Shared swarm_knowledge table + living landscape | 🔲 |
| A.4 | Service boundary prep (message bus, DB abstraction, node registration) | 🔲 |
| A.5 | Multi-node foundation (discovery, federated roster, auth) | 🔲 |
| A.6 | Testing, install wizard, remove hardcoded paths | 🔲 |

### Future Phases

| Phase | Name | Depends On |
|-------|------|------------|
| 4.0-B | Research Assistant / Learning Lab | A complete |
| 4.0-C | Tool Builder | B stable |
| 4.0-D | Distribution (multi-node activation) | A prepared, C stable |

### Feature Tiers (Vibe Coding Wishlist)

| Tier | Features | Status |
|------|----------|--------|
| **Tier 1** | Library transformation (merge Files+Docs, constellation view, gold glow system docs, auto-classification), Memory landscape (force-directed graph), Vortex timeline | 🔲 Not started |
| **Tier 2** | Chat fluidity improvements, Skills drag-drop, Agents overhaul UI | 🔲 Not started |
| **Tier 3** | Email client in-app, Git per-environment UI, Tailscale/VPN integration | 🔲 Not started |

---

## §3 — ARCHITECTURE SNAPSHOT

```
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND  │  Jinja2 + Vanilla JS  │  Views in static/js/  │
│            │  CSS custom props      │  Themes engine         │
├─────────────────────────────────────────────────────────────┤
│  FLASK APP │  34+ blueprints       │  205+ routes           │
│            │  Services layer       │  Pipeline orchestrator  │
├─────────────────────────────────────────────────────────────┤
│  AGENTS    │  17 registered        │  DB-backed registry    │
│            │  Local: Gemma, LLaMA, Qwen, Mistral, Eight     │
│            │  Paid: Nine, Ten, Eleven, Twelve, Thirteen      │
│            │  Service: Duck, Sniffles, Librarian, Scholar    │
├─────────────────────────────────────────────────────────────┤
│  DATA      │  SQLite WAL           │  78+ tables            │
│            │  Agent registry       │  Circuit breaker state  │
├─────────────────────────────────────────────────────────────┤
│  INFRA     │  3 worktrees          │  systemd services      │
│            │  PROD :5050           │  UAT :5052             │
│            │  DEV :5054            │  Ollama :11434          │
└─────────────────────────────────────────────────────────────┘
```

### Key Technical Facts
- **Python 3.12.3** — always use `python3` not `python`
- **Git worktrees**: `/home/seven/swarm` (master/PROD), `/home/seven/swarm-dev` (dev), `/home/seven/swarm-uat` (uat)
- **Vortex** auto-commits on changes via TimeWizard hooks
- **Theme system**: CSS custom properties (`--bg`, `--card`, `--accent`, `--glow-a/b`, `--mist`), named themes in `themes.css`, atmosphere engine injects time-of-day overrides
- **Icon system**: 16×16 SVGs, `stroke="currentColor"`, `fill="none"` — inherits theme colours. NO emoji in UI.
- **Dell Optiplex 7090** refurb, 128GB SSD converted to swap (V-RAM for bigger models), no GPU yet
- **Frontend pattern**: `openWindow(id, title, template)` managed by `winManager`
- **Home screen**: `#home-page` > `#home-header` (sundial + clocks + time + controls) + `#home-content` > `.card-grid`

---

## §4 — DECISION LOG

Architectural and design decisions that affect future work. Newest first.

| Date | Decision | Rationale | Ref |
|------|----------|-----------|-----|
| 16 Apr | All icons must be SVG stroke/currentColor — no emoji | Consistency with theme system; emoji don't change colour with themes | Sundial rewrite |
| 16 Apr | V-RAM (swap) and GPU VRAM added as sundial metrics | 128GB SSD is used for model swap; GPU placeholder for future hardware | diamond.js |
| 16 Apr | Project tracking via single SWARM_PROJECT.md | Stop doc sprawl; agents read one file; sessions start with status check | This file |
| 15 Apr | Agent registry is DB-backed, not hardcoded | 15 dicts across 5 files had drift bugs; DB is single source of truth | P2 registry.py |
| 15 Apr | Circuit breaker pattern for agent dispatch | Prevents cascade failures; fast-fails when Ollama is down | P4 circuit_breaker.py |
| 15 Apr | Local agents route through .chat() not orchestrator | Enables skills_loop for Gemma/Qwen/Eight; matches LLaMA/Mistral pattern | P3a chat.py |
| 15 Apr | Trace troubleshooter via job_id on timeline | Links chat jobs to timeline events for full request tracing | P3b timeline.py |
| 1 Apr | ALM gate is mandatory for mutations | No undocumented changes; proposals are the audit trail | ALM_DRIVER.md |
| 30 Mar | Three-environment workflow (DEV→UAT→PROD) | Agents test in DEV, user validates in UAT, then promotes to PROD | MULTI_STAGE_WORKFLOW.md |
| 30 Mar | Vortex is the single traceability layer | All git, time machine, and audit flows go through Vortex | ARCHITECTURE.md |
| 28 Mar | Documentation-first lifecycle | Every change must be documented; docs are code | ALM_DRIVER.md |
| 28 Mar | One-at-a-time relay queue (not parallel by default) | Prevents resource contention on local hardware; sequential = default | chat.js |

---

## §5 — SESSION LOG

Each session is logged here with date, what was done, and key outcomes.  
**Newest first** — most recent session is always at the top.

---

### Session 16 — 16 April 2026
**Focus:** Sundial fix, SVG icons, V-RAM/GPU metrics, project memory

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Debug sundial not rendering | ✅ Done | Cache issue — system reboot resolved it |
| 2 | Replace emoji with SVG icons | ✅ Done | 8 themed SVG icons, tooltip health dots |
| 3 | Replace Queue metric with V-RAM + GPU | ✅ Done | swap_percent + nvidia-smi detection |
| 4 | Create SWARM_PROJECT.md | ✅ Done | This file — single source of project truth |
| 5 | Create repo memory compact file | ✅ Done | /memories/repo/swarm-project.md |
| 6 | "Fridays as a vibe" concept | 🔲 Pending | Carry forward |

**Commits:** `3fbfc1f` (V-RAM/GPU metrics), `6567e9c` (SVG icons)  
**Tests:** 398 passed, 1 skipped  
**Envs synced:** Yes (master, dev, uat)

---

### Session 15 — 15 April 2026
**Focus:** Phases 1–5 implementation (Fridays BASH plan)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | P1: Fix Tickets tile | ✅ Done | JS was corrupted; rewrote template rendering |
| 2 | P1: Wire Vortex to Git | ✅ Done | git tag on checkpoint, git info in restore |
| 3 | P1: Relay limit default 4→2 | ✅ Done | chat.js + chat.html |
| 4 | P1: True parallel toggle | ✅ Done | Separate exec mode button in chat toolbar |
| 5 | P2: Agent Registry | ✅ Done | 15 dicts → DB, registry.py with 11 accessors |
| 6 | P2: Replace all hardcoded dicts | ✅ Done | services.py, orchestrator.py, memory.py, debate.py, agents.py |
| 7 | P3a: Local agent skill routing | ✅ Done | Gemma/Qwen/Eight via .chat()→skills_loop |
| 8 | P3b: Trace troubleshooter | ✅ Done | job_id timeline, trace API, Trace tile |
| 9 | P4: Circuit breaker | ✅ Done | 3-state per-agent, health probe, stuck-job sweep |
| 10 | P4: Error boundaries | ✅ Done | Consistent timeout handling across all agents |
| 11 | P5.1: Model discovery | ✅ Done | /api/localai/available-models |
| 12 | P5.2: Hot-swap | ✅ Done | /api/agents/hot-swap |
| 13 | P5.3: Import/export | ✅ Done | /api/agents/export-all, /api/agents/import |
| 14 | P5.4: System index + SKILL | ✅ Done | swarm_docs/SYSTEM_INDEX.md auto-generator |
| 15 | P5.5: Cross-referencing | ✅ Done | tickets↔proposals↔conversations linking |

**Tests:** 398 passed, 1 skipped  

---

### Sessions 1–14 — March–April 2026 (Historical)

Detailed records exist in:
- `docs/CHANGELOG.md` — per-session change inventory
- `docs/TASK_TRACKER_LIVE.md` — per-session delta tables (sessions 7–11)
- `docs/audits/AUDIT_TRAIL.md` — audit evidence ledger
- `docs/changes/CHANGELOG_OPERATIONS.md` — operational change ledger

Key milestones from these sessions:
- **Sessions 1–3**: Initial V1 build, 12 agents, Flask monolith, terminal UI
- **Session 4**: World clocks, UI fixes, Telegram DB repair (20 commits)
- **Session 5**: V2 refinement, 26 bugs fixed, BRK-002 timeout fix
- **Session 6**: V3 stabilisation, ALM governance, Time Wizard, 3-stage workflow
- **Session 7**: Identity architecture rewrite, system prompts, cross-references
- **Session 8**: SVG icon overhaul, UI density, trace fix, test repairs
- **Session 9**: Claude Code handover, UAT test scripts
- **Session 10**: Theme architecture separation
- **Session 11**: System validation, notification reliability, Gmail push recovery
- **Sessions 12–14**: Diamond Layer planning, frontend polish, keyboard shortcuts

---

## §6 — DOCUMENT INDEX

All project documentation catalogued by purpose. Agents should consult this to find relevant references.

### Living Documents (Always Current)

| File | Purpose | Update Frequency |
|------|---------|------------------|
| `swarm_docs/SWARM_PROJECT.md` | **This file** — project status, phases, sessions | Every session |
| `docs/ARCHITECTURE.md` | System architecture reference | On structural changes |
| `docs/API_REFERENCE.md` | 205+ route reference (v4.0) | On API changes |
| `docs/BUGS.md` | Bug log with status tracking | On bug discovery/fix |
| `docs/CHANGELOG.md` | Per-session change inventory | Every session |
| `docs/FEATURES_TODO.md` | Feature backlog (30 tasks, 9 phases) | On priority changes |
| `docs/PROJECT.md` | "The coder's bible" — master project doc | On major changes |
| `docs/PHASE_4.0_DIAMOND_LAYER.md` | Diamond Layer + Service Boundaries spec | Active phase |
| `docs/TASK_TRACKER_LIVE.md` | Per-session task delta tables | Every session |
| `swarm_docs/SYSTEM_INDEX.md` | Auto-generated module index | On code changes (SKILL) |
| `swarm_docs/SYSTEM_LANDSCAPE.json` | Machine-readable system map | Auto-generated |

### Governance & Process

| File | Purpose |
|------|---------|
| `docs/ALM_COOKBOOK.md` | Proposal & approval workflow cookbook |
| `docs/ALM_DRIVER.md` | Documentation-first lifecycle rules |
| `docs/DEVELOPER_WORKFLOW.md` | Edit safety rules + Vortex workflow |
| `docs/MULTI_STAGE_WORKFLOW.md` | DEV→UAT→PROD promotion flow |
| `docs/ENVIRONMENTS_REFERENCE.md` | Stage 1/2/3 ports and addresses |
| `docs/DEPLOYMENT_GUIDE.md` | Prereqs, setup, services |
| `docs/registry/FILE_REGISTRY.md` | Master file index |
| `docs/registry/FILING_SYSTEM.md` | Canonical filing standard |
| `docs/runbooks/CHANGE_AND_AUDIT_WORKFLOW.md` | Change → validate → log → audit |
| `docs/runbooks/DOCUMENTATION_LIFECYCLE_WORKFLOW.md` | Doc management runbook |
| `docs/audits/AUDIT_TRAIL.md` | Append-only audit evidence |
| `docs/changes/CHANGELOG_OPERATIONS.md` | Operational change ledger |

### Design References

| File | Purpose |
|------|---------|
| `docs/ARCHITECTURE_DIAGRAM.md` | Mermaid system diagram |
| `docs/POSITIONING_PAPER.md` | Agent personality architecture paper |
| `docs/SYSTEM_CLOCK.md` | Unified time source design |
| `docs/VERSION_CONTROL.md` | Time Machine & versioning strategy |
| `docs/FILE_STRUCTURE.md` | Post-reorg file tree |
| `docs/PROJECT_ANALYSIS.md` | LOC/file analysis (121 files, ~32K LOC) |

### Agent References

| File | Purpose |
|------|---------|
| `docs/AGENT_TWELVE_MANUAL.md` | Agent Twelve operational manual |
| `docs/testing/ALM_TEST_SPECIFICATION.md` | ALM test cases |
| `docs/testing/COMPREHENSIVE_TEST_PLAN_2026-04-01.md` | E2E validation plan |
| `docs/UAT_TEST_SCRIPTS.md` | Reusable UAT test suite |
| `docs/testing/TIME_WIZARD_TESTS.md` | Time Wizard pytest suite |

### API Schemas (JSON)

Located in `docs/api/`: chat.json, governance.json, proposals.json, research.json, studio.json, tools.json, vortex.json

### Historical / Archived

These are point-in-time records. Preserved for audit trail but not actively maintained:

| File | Date | What It Captured |
|------|------|-----------------|
| `docs/AGENT_TASK_ASSIGNMENTS.md` | 28 Mar | Refinement phase task assignments |
| `docs/AGENT_TWELVE_STATUS.md` | 28 Mar | Agent Twelve bootstrap report |
| `docs/APPROVALS_PROPOSALS_STATUS_2026-03-30.md` | 30 Mar | Proposal queue snapshot |
| `docs/AUDIT_MARCH_30_2026.md` | 30 Mar | Session 4 audit (20 commits) |
| `docs/AUDIT_V3_MARCH_28.md` | 28 Mar | V3 system state audit |
| `docs/CLAUDE_CODE_HANDOVER.md` | ~5 Apr | Session 9 handover brief |
| `docs/FRIDAYS_AUDIT_SUMMARY.md` | 28 Mar | "46 errors" investigation |
| `docs/FRIDAYS_BUG_FIX_LOG.md` | 28 Mar | 26-bug refinement audit |
| `docs/FRIDAYS_RESOLUTION_FINAL.md` | 28 Mar | Root cause: commit 606a213 |
| `docs/REFINEMENT_PHASE_SUMMARY.md` | 28 Mar | Refinement handoff |
| `docs/SELF_AUDIT_2026-03-30.md` | 30 Mar | Self-audit snapshot |
| `docs/SESSION_5_COMPLETION_SUMMARY.md` | 29 Mar | Session 5 audit |
| `docs/STATE_SNAPSHOT_2026-03-30_SIGNOFF.md` | 30 Mar | Runtime state sign-off |
| `docs/THEME_ARCHITECTURE_CHANGES.md` | 28 Mar | Theme layer separation |
| `docs/TIME_WIZARD_COMPLETE.md` | 30 Mar | Time Wizard integration report |
| `docs/VS_CODE_CONTEXT.md` | 25 Mar | VS Code context brief |
| `docs/STAGING_WORKFLOW.md` | — | Near-duplicate of MULTI_STAGE_WORKFLOW.md |

---

## §7 — KNOWN PATTERNS & GOTCHAS

Things that have bitten us before. Check this section when debugging.

| Pattern | Detail |
|---------|--------|
| **Browser cache** | Static files (.js, .css) get cached aggressively. Hard refresh or service restart needed after frontend changes. |
| **`python3` not `python`** | System has Python 3.12.3. The `python` command doesn't exist. |
| **Terminal DOM cloning** | `terminal_base.html` is a full SPA shell. Views are `<template>` elements cloned by window manager. Don't add `<script>` inside templates. |
| **Vortex auto-commits** | TimeWizard hooks fire on every `git commit`. Don't be alarmed by `[TimeWizard]` prefixed output. |
| **Services restart** | After backend changes: `sudo systemctl restart swarm-terminal` (PROD) / `swarm-terminal-dev` (DEV). |
| **Three envs must align** | After master commit: `cd /home/seven/swarm-dev && git merge master --no-edit` then same for `swarm-uat`. |
| **Property objects at module level** | Python `property()` only works inside classes. Never use `property()` for module-level lazy values — use functions instead. |
| **Relay limit** | Default is 2, not 4. Changed in P1. |
| **Agent memory tables** | Named `memory_{agent_name}`. Auto-created by registry seed. |
| **Icon pattern** | 16×16 viewBox, `stroke="currentColor"`, `stroke-width="1.3"`, `fill="none"`. See `FRIDAYS_WINDOW_ICON_SVGS` in window-manager.js. |

---

*End of SWARM_PROJECT.md — updated 16 April 2026*
