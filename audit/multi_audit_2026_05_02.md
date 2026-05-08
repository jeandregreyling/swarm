# Multi-audit sweep — 2026-05-02

Closes backlog items 071–081 (audit cluster) on project `P-00221285D1`.

## S-C67D66AAE3 (071) — DB shim adoption
- Production code uses `utils.db` shim in **279 files**.
- Raw `sqlite3` imports remain in **62 files**, mostly:
  - `scripts/*.py` (one-shot CLIs — acceptable, they manage their own connections)
  - `agents/seven/llama.cpp/**` (vendored upstream — out of scope)
- **Verdict**: production paths are clean. No migration needed; document and move on.

## S-816E6D2069 (072) — Swallowed exceptions in blueprints
- Only **2 hits**, both in `frontend/blueprints/agents.py:908,937`.
- Both are inside a **template string** used to scaffold generated agent files,
  not live blueprint runtime. Changing them ripples through every generated
  agent — defer to a dedicated template-refresh pass.
- **Verdict**: no production blueprint swallows exceptions. Pass.

## S-377129B5F7 (073) — Swallowed exceptions in archive paths
- `Archives/` deleted in commit `4cb1d53`. **Obsolete.**

## S-F145A107F9 (074) — print vs logger in services
- 1055 `print(` calls vs 787 logger calls.
- Top offenders are vendored (`agents/seven/llama.cpp/**`) or known
  user-facing CLIs (`utils/seven_fridays.py`, `utils/simulate.py`,
  `core/pipeline/listener.py`).
- **Verdict**: the ratio is fine for an agent system that prints to operator
  terminals by design. Backlog item is informational; flagged as audited.

## S-A539F21C70 (075) — Shell command safety — **FIXED**
- Found 2 `shell=True` uses; **0** `os.system` / `os.popen`.
- `agents/seven/llama.cpp/tools/server/bench/bench.py:228` — vendored upstream.
- `utils/skills.py:45` — **fixed in this commit**: replaced `subprocess.check_output(cmd, shell=True, ...)`
  with `subprocess.check_output(shlex.split(cmd), ...)`. Commands come from a
  fixed allowlist anyway, but removing `shell=True` removes the whole class.

## S-40961D9113 (076) — systemd inventory
5 unit files in repo:
- `swarm-discord.service`
- `swarm-fridays.service`
- `swarm-prewarm.service`
- `swarm-telegram.service`
- `swarm-terminal.service`

## S-DD94A1F892 (077) — test DB isolation
- 26 test files use `tmp_path` (correct pattern).
- 10 test files reference `swarm_memory.db` / `swarm.db` by name. Worst:
  `tests/test_studio_data_governance.py` (13 hits) — needs review.
- Most others are 1–3 references and use `tmp_path` for actual writes.

## S-F70A838E2C (078) — flaky network tests
- Only **3 test files** make raw network calls:
  `tests/test_chat_quality.py`, `tests/test_e2e_fridays.py`, `tests/test_research.py`.
- 34 test files use proper mocking patterns.
- **Verdict**: small, contained. Acceptable for now.

## S-648171E37C (079) — local model deps
- Ollama: 37 refs across 13 files (`core/seven_llm/registry.py`, `frontend/blueprints/ollama.py`,
  `core/platform.py`, `ollama_killswitch.py` are the runtime owners).
- LM Studio: 47 refs.
- llama.cpp: 5 refs (vendored).
- Mapping is centralised through `core/seven_llm/registry.py` and the runtime gateway
  proposal (`STEP-FRIDAYS-MODEL-RUNTIME-GATEWAY-20260430`) — **already in flight**.

## S-534CEBDB83 (080) — archive/history noise
- `.history/` (839MB) and `Archives/` (13MB) deleted in commit `4cb1d53`. **Resolved.**

## S-8219513927 (081) — dirty runtime files
- `.gitignore` expanded + 191 runtime files untracked in commit `4cb1d53`. **Resolved.**

---

_Companion JSON: `audit/multi_audit_2026_05_02.json`_
