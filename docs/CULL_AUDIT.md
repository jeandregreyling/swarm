# Cull audit (2026-10-19)

Rollback point: git tag `pre-cull-20261019` (commit `6f4e3ff91`). Fresh verified database backup outside the repo:
`/mnt/archive/swarm_cold_storage/swarm_memory.20261019.db` (integrity check ok, 2,051 steps).

## Result

| | Before | After |
|---|---|---|
| Repo on disk (excluding `.git` and `.venv`) | 83 GB | 3.8 GB |
| Files tracked by git | 18,554 | about 1,360 |
| Environments running | PROD, DEV, UAT | PROD only (5050) |
| Seven | service on 17777, 71 GB models | removed |

## Deleted, with the evidence

| Item | Size | Evidence it was safe |
|---|---|---|
| `agents/seven/models`, `llama.cpp` | 71 GB | Owner decision. Runtime used a 0.5 GB file; the 70 GB were old model versions. Service stopped first. |
| `agents/seven`, `core/seven`, `core/seven_runtime`, `scripts/seven_runtime_service.py`, `frontend/blueprints/seven_bp.py`, `seven.sh`, the `seven_daily_brief` task | 0.6 MB | Only `seven_bp.py` imported it at load time. Every module that referenced it lazily was import-checked, PROD restarted, all endpoints 200, a chat round-trip worked. |
| `.venv-win/` and `.venv/` tracked in git | 17,156 tracked files | Virtualenvs, regenerable. `.venv` stays on disk, ignored. |
| `*.bak`, `*.bak-*`, `__pycache__`, caches | | Backups of files in git, regenerable. |
| Root logs, `nohup.out`, two junk entries named like shell commands | 1.2 GB | Logs; junk entries were mis-created files. |
| `swarm_memory.db.corrupt.*`, `.recovered`, `.backup.*pre-shell-noise-cleanup`, `swarm.db.retired.*` | 3.3 GB | Live DB passed `quick_check`; fresh backup taken first. |
| `desktop/src-tauri/target` | 3.4 GB | Rust build output, regenerable. |
| `models/Qwen2.5-7B-Instruct` | 0.56 GB | No code references; Ollama keeps its own copies. |
| Android `build/` and `.gradle` | ~0.1 GB | Build output. |
| DEV and UAT processes, `setup_worktrees.sh` | | Owner decision: PROD only. |
| Root files with no importers: `DOES_README.md`, `PIPE_REPAIR_LOG.md`, `proposals.csv`, `rollback_app_center_plan.md`, `Modelfile_Villain_Local` | | Grep for references (excluding docs and records) found none. |

One mistake caught by a test: `proposal_status.py` was deleted and restored, because `from proposal_status import ...` is used by `proposals.py` and the governance module. My first grep only matched file names, not imports. The check is now `^(from|import) <module>`.

## Kept on purpose

| Item | Why |
|---|---|
| `core/seven_llm/` (124 KB) | Despite the name, it is the direct-model runtime the gateway and Watchdog import. Rename, not delete. |
| `artifacts/media_center` (2.6 GB) | Media Center output (AVI/WAV), 83 files from the last three days. This is your content, not mine to delete. |
| `android/` (hive-agent, seven-app sources), `ios/`, `windows/`, `ops/`, `desktop/` sources | Sources are small and referenced by `core/hive` providers, `swarm_platform.py` and the Mac download route. Needs your decision, not a grep. |
| `agents/<parked>` code (gemma, mistral, qwen, llama, duck, eight, nine, twenty and others) | Still imported by routing, the orchestrator and tests. Removing them is a separate change. |
| `.git` (231 MB) | History still holds the old virtualenvs. Shrinking it needs a history rewrite. |

## Still referencing DEV/UAT

About 26 files mention ports 5051/5053 or DEV/UAT: the proposal promotion pipeline
(`proposals_git.py`, `proposal_helpers.py`, `time_machine.py`), `env-banner.js`, `Makefile`,
`utils/config.py`. They are inert with only PROD running, but not removed.

## Findings

- Apex's capability grants were missing after the swap script ran; fixed in the script and the database.
- Tests are now pinned to the Fred seat via `tests/conftest.py`, so the live switch file does not change test results.
