Cline
P-308466EE76# SWARM Full Codebase Audit — 2026

**Status:** active  
**Owner:** Seven  
**Created:** 2026-05-10  
**Source audit plan:** `audit/AUDIT_PLAN_20260510.md`  
**Results file:** `audit/AUDIT_RESULTS_20260510.md`

---

## Overview

Full-codebase audit of the SWARM multi-agent orchestration system. Covers code quality,
test posture, architecture, security, operations, agent ecosystem, frontend, hardcoded paths,
dependencies, and documentation continuity. Observation-first — no changes during planning.

---

## Packets

- [ ] Area 1 — Code Quality & The Standard: run `make bullshit`, `make excellent`, check Forbidden List violations, confirm pillar blueprints have `summary_for_seven()`, confirm wishlist tiles have correct `data-wishlist-status`
- [ ] Area 2 — Test Posture: identify tests hitting real DB paths, run network-dependent tests in isolation, check `test_studio_data_governance.py`, spot-check session28 batch series, confirm watchdog/vortex tests pass, review y44–y59 regression files
- [ ] Area 3 — Architecture & Routing: review `core/spine.py` (stall/timeout), `core/routing.py` (determinism/logging), `core/model_runtime_gateway.py` (lock contention), `frontend/blueprints/chat.py` (watchdog handoff), `frontend/services/chat_jobs.py` (stale job reaping), `core/time_machine.py` (no git commits), `fridays/task_runner.py` (hardcoded paths)
- [ ] Area 4 — Security & Secrets: scan git log for secret commits, verify `.gitignore` coverage, grep for hardcoded API keys, review `auth_2fa.py` and `auth_rate_limit.py` wiring, review `swarm_governance.py`, check killswitch completeness, confirm pre-commit hook blocks RED
- [ ] Area 5 — Operations & Deployment: inspect all 5 systemd unit files, confirm dev/UAT service files exist, review Makefile `deploy` target merge safety, review `ops/doctor.py` and `ops/integration_health.py` probe coverage, review `ops/bullshit_detector.py` scoring, check `swarm-prewarm.sh` failure behaviour
- [ ] Area 6 — Agent Ecosystem: categorise all 20+ agents (active/dormant/vendored), spot-check 3–4 for Forbidden List issues, check `skill_intent.py` / `skills_loop.py` wiring, review `agents/seven/` persona components, confirm daemon agents are systemd-controlled only
- [ ] Area 7 — Frontend & UI Standard: check `terminal_base.html` pillar tile attributes, scan JS views for unguarded `console.log`, check all `fetch` calls for `.catch()` error state handlers, confirm pillar dashboards handle empty DB, review `/api/health` structure
- [ ] Area 8 — Hardcoded Path Debt: confirm three priority targets still unfixed (`fridays/task_runner.py`, `fridays/scheduler.py`, `lib/system/file_versioning.py`), re-run path scan and compare count to 149/67 baseline, assess agent-bucket portability risk
- [ ] Area 9 — Dependency & Runtime Health: review `requirements.txt` and `pyproject.toml` for floating pins, run `pip check` / `pip list --outdated`, check `nohup.out` for secret leakage, review `core/seven_llm/registry.py` for bypass paths
- [ ] Area 10 — Documentation Continuity: identify all "Moved into Studio" stubs, assess repo self-documentability for new developers, confirm key docs are real content not stubs, review E2E paper trail files for traceability value

---

## Execution Order

| Priority | Packet | Effort | Risk if skipped |
|---|---|---|---|
| 1 | Area 1 — Code Quality & The Standard | Low | Broken contract |
| 2 | Area 4 — Security & Secrets | Low | Public exposure |
| 3 | Area 2 — Test Posture | Medium | Silent regressions |
| 4 | Area 3 — Architecture & Routing | High | Runtime failures |
| 5 | Area 5 — Operations & Deployment | Medium | Bad deploys |
| 6 | Area 7 — Frontend & UI Standard | Medium | UX regressions |
| 7 | Area 6 — Agent Ecosystem | High | Dead/broken agents |
| 8 | Area 8 — Hardcoded Path Debt | Low | Portability |
| 9 | Area 9 — Dependency & Runtime Health | Low | Dependency drift |
| 10 | Area 10 — Documentation | Low | Onboarding gap |

---

## Blackboard

- Previous audit covered backlog items 071–081 (`audit/multi_audit_2026_05_02.md`, `audit/hardcoded_paths_audit.md`)
- 149 hardcoded `/home/seven/swarm` references across 67 files found in prior scan — SWARM_ROOT not yet adopted in three priority files
- 13 raw DB hits in `tests/test_studio_data_governance.py` flagged in issue 077 — unresolved
- Vendored `agents/seven/llama.cpp/**` is explicitly OUT OF SCOPE
- Results to be written to `audit/AUDIT_RESULTS_20260510.md` as each area completes
