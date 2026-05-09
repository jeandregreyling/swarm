# SWARM Full Codebase Audit Results — 2026-05-10

**Project:** P-308466EE76 | **Agent:** Cline (eighteen) | **Status:** In Progress

---

## Area 1 — Code Quality & The Standard ✅

| Check | Result |
|-------|--------|
| `make bullshit` | GREEN 97/100 |
| `make excellent` | All session28 batches green (1 skip in slash commands) |
| Forbidden List violations | 0 critical, 0 warnings |
| Pillar blueprints `summary_for_seven()` | Spot-check deferred to Area 6 |
| Wishlist tile attributes | Spot-check deferred to Area 7 |

**Verdict:** Build is up to standard. No action required.

---

## Area 2 — Test Posture ✅

| Check | Result |
|-------|--------|
| `tests/test_studio_data_governance.py` (#077) | **False positive** — uses `tmp_path` + `monkeypatch` correctly. The 13 "hits" are string literals in assertions, not raw DB connections. |
| New test file added | `tests/test_swarm_root_priority_files.py` — 9 tests, all passing |
| Network-dependent tests | 3 files identified (acceptable, contained) |

**Verdict:** Test posture is sound. No raw DB writes in production tests.

---

## Area 8 — Hardcoded Path Debt ✅ (Priority Files)

**Baseline:** 149 hardcoded `/home/seven/swarm` references across 67 files.

**Fixed in this pass — 3 priority files:**

| File | Hits Before | Fix Applied |
|------|-------------|-------------|
| `fridays/task_runner.py` | 3 | `_SWARM_ROOT` env + `__file__` auto-detect; backup script paths also converted |
| `fridays/scheduler.py` | 4 | `_SWARM_ROOT` for root, utils, lib/email, core `sys.path` inserts |
| `lib/system/file_versioning.py` | 6 | `_SWARM_ROOT` for dirs + docstring examples cleaned |

**Test coverage:** `tests/test_swarm_root_priority_files.py` proves:
- No literal `/home/seven/swarm` remains in the 3 files
- `SWARM_ROOT` env override correctly redirects paths

**Remaining debt:** ~146 references across 64 files (non-runtime-critical paths: agents, tests, scripts).

---

## Area 3 — Architecture & Routing ✅

**Critical fix: `core/knowledge/projects.py` `_emit_spine()` kwarg mismatch**

| Check | Result |
|-------|--------|
| Spine event emission | **BROKEN** — `_emit_spine()` passed `summary`/`detail` but `core.spine.log()` expects `message`/`payload`. Silent failure (exception swallowed). |
| Impact | Every project mutation (create, add_step, update_status, blackboard note) silently failed to emit TICKET events into Vortex. |
| Fix | Corrected kwargs in `_emit_spine()` to use `message`/`payload`. |
| Test | `tests/test_projects_emit_spine.py` — 3 tests, all green. |

**Verdict:** Critical silent failure fixed. Root cause of "no updates / rejection" symptom on Samsung→Potato-1 connections.

---

## Area 4 — Security & Secrets ✅

### Checks Performed

| Check | Result |
|-------|--------|
| `python3 scripts/secret_scan.py` | **PASSED** — no tracked secrets or known key patterns |
| `.gitignore` coverage | ✅ Comprehensive: `.env*`, `*_credentials.json`, `*_token.json`, `*_password.txt`, `*tokens*.jsonl`, `*.db`, `.secret_key` |
| `nohup.out` secret leakage | ✅ Empty (0 bytes) — no leaked output |
| Git history — secret commits | ✅ `2a89cd04` removed tracked env files; no re-introduction since |
| Pre-commit hook | ✅ `swarm-secret-scan` runs `scripts/secret_scan.py` — covers 10 provider patterns (GitHub, Groq, HuggingFace, OpenAI, Anthropic, Google, Tavily, Slack, SendGrid, private keys) |
| `SECURITY.md` | ✅ Adequate public-repo policy (credential rotation, removal, history compromise) |
| `core/auth_2fa.py` | ✅ Pure stdlib TOTP (RFC 6238), `hmac.compare_digest` for timing-safe comparison, DB path configurable via `SWARM_2FA_DB` env var |
| `core/auth_rate_limit.py` | ✅ Fixed-window per-IP limiter, thread-safe (`RLock`), JSON audit log to `audit/auth.log` |

### Bugs Found & Fixed

| Bug | Severity | File | Fix |
|-----|----------|------|-----|
| `kill_switch.py` used broken `from utils.database import get_connection` (shim does `from db import *` → `ModuleNotFoundError`) | **HIGH** — reset_agent, pause, resume all silently fail | `core/kill_switch.py` (3 locations) | Changed to `from utils.db._connection import get_connection` |
| `killswitch.sh` hardcoded `/home/seven/swarm/ollama_killswitch.py` | **MEDIUM** — fails on non-default install paths | `killswitch.sh` line 24 | Uses `SWARM_ROOT` env with `dirname "$0"` fallback |

### Observations (no fix needed)

- `kill_switch.py` imports `utils.config` at module level (line 18–19) — if `config.py` is missing, entire module fails to import. This is acceptable since `config.py` is a deployment prerequisite.
- KillSwitch API endpoints (`/api/killswitch/emergency` etc.) have no auth check in the method itself — authentication is expected to be enforced by the Flask blueprint layer. Verified this is standard pattern in the codebase.

### Test Coverage

New test file: `tests/test_security_audit_area4.py` — 8 tests, all passing.

**Verdict:** Secret hygiene is solid. Two real bugs fixed in kill switch infrastructure. `make bullshit` GREEN 97/100 unchanged.

---

## Areas Pending (5, 6, 7, 9, 10)

- Area 5 — Operations & Deployment
- Area 6 — Agent Ecosystem
- Area 7 — Frontend & UI Standard
- Area 9 — Dependency & Runtime Health
- Area 10 — Documentation Continuity

---

*Next action: proceed with Area 5 (Operations & Deployment) based on audit plan priority.*
