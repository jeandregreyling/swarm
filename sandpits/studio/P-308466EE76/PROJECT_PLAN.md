# SWARM Full Codebase Audit — 2026 (P-308466EE76)
**Status:** Complete
**Owner:** Seven | **Methodology:** Observation-first audit

## Change Log (Plain English - What, When, Why)
**May 10, 2026 - Audit Plan Created**
- Picked up from prior audits (071–081) in `audit/multi_audit_2026_05_02.md` and `audit/hardcoded_paths_audit.md`.
- Widened lens to cover all 10 areas: code quality, test posture, architecture/routing, security, ops/deployment, agent ecosystem, frontend/UI, hardcoded path debt, dependency health, and documentation continuity.
- Results will land in `audit/AUDIT_RESULTS_20260510.md` as each area completes.
- **Why:** Ensure SWARM honours its own Standard contract and surfaces any public-exposure risks before the next production cycle.

**May 10, 2026 - Area 1 Complete + Hardcoded Path Debt (3 priority files fixed)**
- `make bullshit` GREEN 97/100. `make excellent` all green (one skip in slash commands).
- Verified `tests/test_studio_data_governance.py` uses `tmp_path` + `monkeypatch` correctly — issue #077 (13 raw DB hits) is a **false positive** (string literals in assertions, not actual DB connections).
- Fixed hardcoded `/home/seven/swarm` paths in 3 priority files:
  - `fridays/task_runner.py`: module-level `sys.path.insert` + 2 backup task script paths now use `_SWARM_ROOT`
  - `fridays/scheduler.py`: module-level `sys.path.insert` (3 locations: root, utils, lib/email, core) now use `_SWARM_ROOT`
  - `lib/system/file_versioning.py`: module-level `sys.path.insert` + `VERSIONS_DIR` + `RESTORE_BIN_DIR` now use `_SWARM_ROOT`
- Added `tests/test_swarm_root_priority_files.py` (9 tests) proving no literal remains and env override works.
- All 9 new tests pass; bullshit detector unchanged at GREEN.

## Steps (Execution Order by Risk)
- [x] Area 1 — Code Quality & The Standard: run `make bullshit` + `make excellent`, check Forbidden List violations, confirm `summary_for_seven()` on pillar blueprints, confirm wishlist tiles have `data-wishlist-status="active-v0"`
- [x] Area 4 — Security & Secrets: secret scan PASSED, `.gitignore` comprehensive, `nohup.out` empty, pre-commit hook covers 10 providers. **Fixed:** `core/kill_switch.py` broken `utils.database` import → `utils.db._connection` (3 locations, HIGH severity — reset/pause/resume all silently failed); `killswitch.sh` hardcoded path → `SWARM_ROOT` + `dirname` fallback. Test: `tests/test_security_audit_area4.py` (8 tests, all green). `make bullshit` GREEN 97/100 unchanged.
- [x] Area 2 — Test Posture: identify tests writing to real DB (not `tmp_path`), run network-dependent tests in isolation, check `test_studio_data_governance.py` (13 raw DB hits flagged #077), spot-check session28 batch series, review y44–y59 regression files
- [x] Area 3 — Architecture & Routing: **CRITICAL FIX** — `core/knowledge/projects.py` `_emit_spine()` passed wrong kwargs (`summary`/`detail`) to `core.spine.log()` which expects (`message`/`payload`). Because the helper swallows all exceptions, every project mutation (create, add_step, update_status, blackboard note) silently failed to emit TICKET events into Vortex. This was the root cause of the "no updates /卡顿 / rejection" symptom observed on Samsung→Potato-1 connections. Fixed + regression test `tests/test_projects_emit_spine.py` (3 tests, all green). `make bullshit` GREEN 97/100 unchanged.
- [x] Area 5 — Operations & Deployment: 6 systemd units present, `make deploy` chains test→sync→restart, `wake-dev`/`wake-uat` targets exist, `pip check` clean. Hardcoded paths in .service files are expected (systemd design). Test: 5 new tests in `test_audit_areas_5_to_10.py`.
- [x] Area 7 — Frontend & UI Standard: 5 `data-wishlist-status` attributes in `terminal_base.html`, DOMPurify + `safeMarkdown()` XSS protection, 0 `console.log` in base, only 1 view uses `fetch()` (`feeds.html`) with more `.catch` than fetch calls. Test: 6 new tests.
- [x] Area 6 — Agent Ecosystem: 25 agent directories, `skill_intent.py` routing works (creative vs operational), `skills_loop.py` (440 lines) shared by paid agents. No Forbidden List violations. Test: 5 new tests.
- [x] Area 8 — Hardcoded Path Debt: confirm three priority files still unfixed (`fridays/task_runner.py`, `fridays/scheduler.py`, `lib/system/file_versioning.py`), re-run scan vs 149-reference / 67-file baseline
- [x] Area 9 — Dependency & Runtime Health: ⚠️ **No version pins** in `requirements.txt` or `pyproject.toml` — all float. `pip check` clean today. `nohup.out` empty. Python >=3.11 enforced. Flagged for future sprint. Test: 4 new tests.
- [x] Area 10 — Documentation Continuity: ⚠️ 10 of 18 top-level docs are "Moved into Studio" stubs (6 lines each). 7 docs have real content (the-standard, getting-started, wishlist-pillars, continuous-improvement, HIVE_VISION, HIVE_PRODUCTION_PLAN, NODE_RESOURCE_CONTRACT). Stubs lack discoverability breadcrumbs. Test: 3 new tests.
- [x] **Area 11 — Samsung Device Porting (ad-hoc)**:
  - **What:** Ported Hive Agent to properly detect and advertise Samsung NPU/GPU capabilities so SWARM scheduler can route TFLite inference jobs to Samsung tablets/phones.
  - **Files touched:**
    - `android/hive-agent/app/src/main/java/com/swarm/hive/AndroidSampler.kt` — added `gpuPresent()`, `npuPresent()`, `capabilities()` methods with Samsung-specific driver/SoC detection.
    - `android/hive-agent/app/src/main/java/com/swarm/hive/HiveAgentService.kt` — replaced hardcoded `["inference.cpu"]` with dynamic `sampler.capabilities()`.
    - `core/hive/providers/android.py` — mirrored Samsung/NPU detection for Termux path; added `inference.tflite` to base capabilities; made `gpu_present` and `npu_present` dynamic in `compute()`.
    - `tests/test_hive_android_provider.py` — added 8 new tests covering GPU presence, NPU detection via driver/SOC/generic NNAPI, capability lists, and compute flags.
    - `docs/NODE_RESOURCE_CONTRACT.md` — documented Samsung/Android capability detection rules.
  - **Test results:** 25/25 tests in `test_hive_android_provider.py` pass; `make bullshit` GREEN 97/100 (unchanged).
  - **Why:** User requested Samsung device integration to leverage NPU processing power within the SWARM Hive environment. The scheduler previously saw Android nodes as `inference.cpu` only, under-utilising Samsung hardware.

## Blackboard Notes
- ~~Prior audit baseline: 149 hardcoded `/home/seven/swarm` references across 67 files — SWARM_ROOT not adopted yet in three priority files.~~ **FIXED May 10:** 3 priority files (`task_runner.py`, `scheduler.py`, `file_versioning.py`) now use `_SWARM_ROOT`. Remaining ~146 refs in 64 files are non-runtime-critical (agents, tests, scripts).
- ~~13 raw DB hits in `tests/test_studio_data_governance.py` — flagged issue 077, still unresolved.~~ **CLOSED May 10:** False positive — test correctly uses `tmp_path` + `monkeypatch`.
- `agents/seven/llama.cpp/**` is OUT OF SCOPE (vendored).
- Source audit plan: `audit/AUDIT_PLAN_20260510.md`
- Results file: `audit/AUDIT_RESULTS_20260510.md`
- New test file: `tests/test_swarm_root_priority_files.py` (9 tests, all green)
