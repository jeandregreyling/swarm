# SWARM Full Codebase Audit — 2026 (P-308466EE76)
**Status:** Active
**Owner:** Seven | **Methodology:** Observation-first audit

## Change Log (Plain English - What, When, Why)
**May 10, 2026 - Audit Plan Created**
- Picked up from prior audits (071–081) in `audit/multi_audit_2026_05_02.md` and `audit/hardcoded_paths_audit.md`.
- Widened lens to cover all 10 areas: code quality, test posture, architecture/routing, security, ops/deployment, agent ecosystem, frontend/UI, hardcoded path debt, dependency health, and documentation continuity.
- Results will land in `audit/AUDIT_RESULTS_20260510.md` as each area completes.
- **Why:** Ensure SWARM honours its own Standard contract and surfaces any public-exposure risks before the next production cycle.

## Steps (Execution Order by Risk)
- [ ] Area 1 — Code Quality & The Standard: run `make bullshit` + `make excellent`, check Forbidden List violations, confirm `summary_for_seven()` on pillar blueprints, confirm wishlist tiles have `data-wishlist-status="active-v0"`
- [ ] Area 4 — Security & Secrets: scan git log for secret commits, verify `.gitignore` coverage, grep for hardcoded API keys, review `auth_2fa.py` + `auth_rate_limit.py` wiring, check killswitch completeness, confirm pre-commit hook blocks RED
- [ ] Area 2 — Test Posture: identify tests writing to real DB (not `tmp_path`), run network-dependent tests in isolation, check `test_studio_data_governance.py` (13 raw DB hits flagged #077), spot-check session28 batch series, review y44–y59 regression files
- [ ] Area 3 — Architecture & Routing: review `core/spine.py` stall/timeout, `core/routing.py` determinism, `core/model_runtime_gateway.py` lock contention, `frontend/blueprints/chat.py` watchdog handoff, `frontend/services/chat_jobs.py` stale job reaping, `core/time_machine.py` no-git-commit policy
- [ ] Area 5 — Operations & Deployment: inspect all 5 systemd units, confirm dev/UAT service files exist, review Makefile `deploy` merge safety, review `ops/doctor.py` + `ops/integration_health.py` coverage, review `ops/bullshit_detector.py` scoring
- [ ] Area 7 — Frontend & UI Standard: check `terminal_base.html` pillar tile attributes, scan JS views for unguarded `console.log`, verify all `fetch` calls have `.catch()` error state handlers, confirm pillar dashboards handle empty DB
- [ ] Area 6 — Agent Ecosystem: categorise 20+ agents (active/dormant/vendored), spot-check 3–4 for Forbidden List issues, check `skill_intent.py` / `skills_loop.py` routing wiring, review `agents/seven/` persona components
- [ ] Area 8 — Hardcoded Path Debt: confirm three priority files still unfixed (`fridays/task_runner.py`, `fridays/scheduler.py`, `lib/system/file_versioning.py`), re-run scan vs 149-reference / 67-file baseline
- [ ] Area 9 — Dependency & Runtime Health: review `requirements.txt` + `pyproject.toml` for floating pins, run `pip check`, check `nohup.out` for secret leakage, review `core/seven_llm/registry.py` for bypass paths
- [ ] Area 10 — Documentation Continuity: identify all "Moved into Studio" stubs, assess repo self-documentability for new developers, confirm key docs are real content not stubs

## Blackboard Notes
- Prior audit baseline: 149 hardcoded `/home/seven/swarm` references across 67 files — SWARM_ROOT not adopted yet in three priority files.
- 13 raw DB hits in `tests/test_studio_data_governance.py` — flagged issue 077, still unresolved.
- `agents/seven/llama.cpp/**` is OUT OF SCOPE (vendored).
- Source audit plan: `audit/AUDIT_PLAN_20260510.md`
- Results file: `audit/AUDIT_RESULTS_20260510.md`
