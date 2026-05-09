# SWARM Audit Plan — 2026-05-10

**Prepared by:** Fresh-eyes review pass (no prior context assumed)  
**Scope:** Full codebase review — architecture, code quality, security, testing, operations  
**Method:** Observation only. No changes made during planning. Findings are areas to investigate, not verdicts.

---

## Context

SWARM is a local-first multi-agent orchestration system. It runs a Flask web UI,
routes chat to local (Ollama, LM Studio, llama.cpp) and cloud LLMs, maintains
project memory in SQLite, and provides a "Hive" for multi-device enrolment. The
primary AI persona is **Seven**. The repo is public and self-described as
*not production-ready*.

Previous audits exist (`audit/multi_audit_2026_05_02.md`, `audit/hardcoded_paths_audit.md`)
and cover items 071–081 of an internal backlog. This plan picks up where those left off
and widens the lens.

---

## Audit Areas

### Area 1 — Code Quality & The Standard

**Why:** The project defines an explicit contract (`docs/the-standard.md`) with a
Forbidden List and a Single Stamp checklist. The first thing to verify is whether
the living codebase actually honours that contract.

**What to review:**

- [ ] Run `make bullshit` and capture the full report. Confirm exit code and stamp colour.
- [ ] Run `make excellent` end-to-end and tally which batch files pass/fail.
- [ ] Check for Forbidden List violations manually in non-exempt paths:
  - `TODO` / `FIXME` / `HACK` / `XXX` in `core/`, `frontend/blueprints/`, `fridays/`, `agents/` (non-vendored).
  - `pass  # placeholder` or `pass  # stub` patterns.
  - `raise NotImplementedError` outside ABCs.
  - Bare `except:` clauses.
  - `print("debug…")` / `print("test…")` in non-test Python.
  - Hard-coded `127.0.0.1` / `localhost` in non-config paths.
- [ ] Confirm every pillar blueprint (`cybersecurity_bp.py`, `financial_bp.py`, `trading_bp.py`, `business_bp.py`) has a `summary_for_seven()` callable.
- [ ] Confirm every pillar tile in `terminal_base.html` carries `data-wishlist-status="active-v0"`.

---

### Area 2 — Test Posture

**Why:** There are ~180 test files. Previous audit (077) found 10 tests referencing
`swarm_memory.db` / `swarm.db` by name instead of `tmp_path`. That's a contamination risk.

**What to review:**

- [ ] Identify all test files that reference a real DB path (`swarm_memory.db`, `swarm.db`) without `tmp_path` — confirm which are actually writing vs. just referencing.
- [ ] Run the three network-dependent tests (`test_chat_quality.py`, `test_e2e_fridays.py`, `test_research.py`) in isolation; confirm they gracefully skip or mock when the network is unavailable.
- [ ] Check `tests/test_studio_data_governance.py` (flagged 13 raw DB hits in 077) — is it actually writing to prod DB?
- [ ] Spot-check the `test_session28_batch*` series (3–16) for assertion quality: are tests meaningful or just `assert True` / smoke-only?
- [ ] Confirm `tests/test_watchdog_repair_lessons.py` and `tests/test_vortex_heartbeat_git_guard.py` (cited in README as priority) pass cleanly.
- [ ] Review the `y44`–`y59` test files — these appear to be regression/patch tests. Check coverage isn't just duplicating batch tests.

---

### Area 3 — Architecture & Routing

**Why:** SWARM routes chat through `core/routing.py` and `core/spine.py`, with
a model runtime gateway layer (`core/model_runtime_gateway.py`). Multi-node hive,
agent relay, and local model coordination all live here. This is the highest-risk
area for race conditions and silent failures.

**What to review:**

- [ ] Read `core/spine.py` — how does it handle a stalled agent? Is there a timeout path?
- [ ] Read `core/routing.py` — is the routing decision tree deterministic and logged?
- [ ] Read `core/model_runtime_gateway.py` — how are local model loads/unloads managed? Any lock contention risk?
- [ ] Read `frontend/blueprints/chat.py` — watchdog integration: does it correctly hand off to `watchdog_repair_lessons`?
- [ ] Read `frontend/services/chat_jobs.py` — job queue hygiene: are stale jobs reaped?
- [ ] Check `core/time_machine.py` — confirm Vortex checkpoints do NOT write Git commits or tags (per `SECURITY.md` policy).
- [ ] Verify `fridays/task_runner.py` — does it have the hardcoded path issues identified (3 hits) and is it on the fix list?

---

### Area 4 — Security & Secrets

**Why:** The repo is public. There was a historical incident where local runtime secret
files were tracked. The README and SECURITY.md acknowledge this.

**What to review:**

- [ ] Run `git log --oneline | head -50` — look for any commit messages referencing secrets, tokens, or `.env` files.
- [ ] Check `.gitignore` — confirm all known secret file patterns are excluded (`.env*`, `*.db`, `*.jsonl`, `token*`).
- [ ] Scan for any hardcoded API keys or tokens in non-test Python: `grep -r "sk-" --include="*.py"`, `grep -r "Bearer " --include="*.py"`.
- [ ] Review `core/auth_2fa.py` and `core/auth_rate_limit.py` — are these wired into the live Flask app or dead code?
- [ ] Review `swarm_governance.py` — what does it govern and is it enforced at runtime?
- [ ] Check `killswitch.sh` and `core/kill_switch.py` — do they actually terminate all services cleanly or just send SIGTERM?
- [ ] Confirm the pre-commit hook (`scripts/install-hooks.sh`) is present and blocks RED commits.

---

### Area 5 — Operations & Deployment

**Why:** Five systemd units are in the repo. There are three worktrees (PROD, DEV, UAT).
The Makefile shows the deployment chain. With live services, the risk of a bad deploy
affecting running users is real.

**What to review:**

- [ ] Inspect each `.service` file (`swarm-discord`, `swarm-fridays`, `swarm-prewarm`, `swarm-telegram`, `swarm-terminal`) — confirm `WorkingDirectory`, `User`, `Restart`, `ExecStart` are sane.
- [ ] Confirm `swarm-terminal-dev` and `swarm-terminal-uat` service files exist (referenced in Makefile but not in file listing — may be untracked or on-host only).
- [ ] Check `Makefile` `deploy` target — it calls `test → sync → restart`. Does `sync` handle merge conflicts safely?
- [ ] Review `ops/doctor.py` — what does the health check actually probe? Is it covering all four pillars?
- [ ] Check `ops/integration_health.py` — same question: does it catch a dead Ollama or LM Studio daemon?
- [ ] Review `ops/bullshit_detector.py` — understand its scoring logic to know if a GREEN stamp is meaningful or easily gamed.
- [ ] Check `swarm-prewarm.sh` and `swarm_prewarm.service` — what does pre-warming do and what happens if it fails?

---

### Area 6 — Agent Ecosystem

**Why:** There are 20+ agent directories under `agents/`. Quality is likely uneven.
Some may be stubs; others are production-routed.

**What to review:**

- [ ] List and categorise all agents by status: active (routed), dormant (not routed), vendored (llama.cpp).
- [ ] Spot-check 3–4 agent files for the Forbidden List violations — particularly any with `TODO`, `pass`, or missing error handling.
- [ ] Check `agents/skill_intent.py` and `agents/skills_loop.py` — are these wired into the routing layer or standalone?
- [ ] Review `agents/seven/` specifically — this is the primary LLM persona. Check `self_awareness`, `learnings`, and `composer` components for any obvious quality issues.
- [ ] Confirm the `fridays/` daemon agents (Discord bot, Telegram bot, scheduler) are not running unconditionally — they should be controlled by their respective systemd units.

---

### Area 7 — Frontend & UI Standard

**Why:** `docs/the-standard.md` §4 requires every panel to render 4 states: Loading,
Empty, Error, Populated. The UI standard also mandates keyboard accessibility and
aria-labels. These are hard to verify without running the app but can be partially
audited statically.

**What to review:**

- [ ] Open `frontend/templates/terminal_base.html` — confirm all four pillar tiles have correct `data-wishlist-status` and `data-live-slug` attributes.
- [ ] Spot-check `frontend/static/js/views/` for `console.log` outside `window.__SWARM_DEBUG` guards.
- [ ] Check all `fetch` calls in JS views — do they have `.catch()` handlers that render an Error state, or do they silently fail?
- [ ] Confirm the four pillar dashboard views each handle empty DB gracefully (no blank panel).
- [ ] Review `frontend/blueprints/health_bp.py` — does `/api/health` return a properly structured four-pillar + Seven + build response?

---

### Area 8 — Hardcoded Path Debt

**Why:** The previous audit found 149 hardcoded `/home/seven/swarm` references across
67 files. The recommendation was to use `SWARM_ROOT`. Three high-leverage targets were
identified but not yet fixed.

**What to review:**

- [ ] Confirm the three priority targets are still unfixed: `fridays/task_runner.py`, `fridays/scheduler.py`, `lib/system/file_versioning.py`.
- [ ] Re-run the path scan and check if the count has grown or shrunk since 2026-05-02.
- [ ] Assess whether any of the agent-bucket paths (59 hits) would actually break on a different machine.

---

### Area 9 — Dependency & Runtime Health

**Why:** The project runs Ollama, LM Studio, and llama.cpp locally. `requirements.txt`
and `pyproject.toml` define the Python layer. Drift between declared and actual
dependencies is a silent failure risk.

**What to review:**

- [ ] Read `requirements.txt` and `pyproject.toml` — are versions pinned or floating? Any `>=` pins that could silently pull breaking changes?
- [ ] Check if a `pip check` or `pip list --outdated` reveals known CVEs or incompatibilities.
- [ ] Confirm `nohup.out` (present in root) isn't leaking sensitive runtime output — check last 20 lines.
- [ ] Review `core/seven_llm/registry.py` — is the local model registry the single source of truth for Ollama/LM Studio routing, or are there bypass paths?

---

### Area 10 — Documentation & Knowledge Continuity

**Why:** Several core docs have been "moved to Studio" (a separate knowledge management
system) and replaced with stub files. This creates a gap for anyone reviewing the repo
without Studio access.

**What to review:**

- [ ] Identify all docs replaced by the "Moved into Studio" stub (`.instructions.md`, `docs/ARCHITECTURE.md`, `docs/CODING_BIBLE.md`, and likely others).
- [ ] Assess whether the repo is still self-documenting without Studio access — can a new developer onboard from the repo alone?
- [ ] Confirm `docs/getting-started.md`, `docs/AGENTS.md`, `docs/API_REFERENCE.md`, and `docs/DEVELOPER_GUIDE.md` are actual content or also stubs.
- [ ] Review `audit/E2E_PAPER_TRAIL_*` files — do they provide useful traceability or are they generated noise?

---

## Execution Order (Recommended)

| Priority | Area | Effort | Risk if skipped |
|---|---|---|---|
| 1 | Area 1 — Code Quality & The Standard | Low (run make) | Broken contract |
| 2 | Area 4 — Security & Secrets | Low (grep + git log) | Public exposure |
| 3 | Area 2 — Test Posture | Medium | Silent regressions |
| 4 | Area 3 — Architecture & Routing | High | Runtime failures |
| 5 | Area 5 — Operations & Deployment | Medium | Bad deploys |
| 6 | Area 7 — Frontend & UI Standard | Medium | UX regressions |
| 7 | Area 6 — Agent Ecosystem | High | Dead/broken agents |
| 8 | Area 8 — Hardcoded Path Debt | Low | Portability |
| 9 | Area 9 — Dependency & Runtime Health | Low | Dependency drift |
| 10 | Area 10 — Documentation | Low | Onboarding gap |

---

## What This Plan Is NOT

- It is not a verdict. Nothing has been run yet.
- It is not an indictment. The existing audit trail shows active, disciplined maintenance.
- It is not exhaustive. Vendored code (`agents/seven/llama.cpp/**`) is explicitly out of scope.

---

## Output of Each Area

Each area, when executed, should produce:
1. A **finding summary** (pass / attention / fix-required).
2. Specific file paths and line numbers for anything needing work.
3. A recommended action (document, defer, or fix).

Results will be written to `audit/AUDIT_RESULTS_20260510.md` as each area completes.

---

_Plan version: 1.0 — ready for owner review before execution begins._
