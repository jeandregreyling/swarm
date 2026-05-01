# Hardcoded /home/seven/swarm path audit

**Total hits**: 149 across 67 files

_Generated 2026-05-02 by S-7C7ED96F5B; excludes `.history/`, `Archives/`, `desktop/`, `sandpits*/`, `runtime/`, and `tests/test_notification_reliability.py`._

## By bucket

- **agent**: 59
- **test**: 29
- **fridays**: 24
- **lib**: 22
- **utils**: 10
- **scripts**: 3
- **sandpit**: 1
- **frontend**: 1

## Top files (≥3 hits)

- `utils/seven_fridays.py` — 6
- `tests/test_triage_queue_dryrun.py` — 6
- `fridays/discord_bot.py` — 6
- `lib/system/file_versioning.py` — 6
- `tests/test_telegram_trust.py` — 4
- `fridays/scheduler.py` — 4
- `fridays/telegram_bot.py` — 4
- `fridays/skills.py` — 4
- `agents/ghost/duck.py` — 4
- `agents/specialists/eight_memory.py` — 4
- `agents/ghost_coder/ghost_coder_agent.py` — 4
- `tests/test_direct_agent_commands.py` — 3
- `tests/test_channel_smoke.py` — 3
- `fridays/task_runner.py` — 3
- `agents/ten/copilot_agent.py` — 3
- `agents/ghost/sniffer.py` — 3
- `agents/nineteen/nineteen_agent.py` — 3
- `agents/llama/llama_agent.py` — 3
- `agents/scholar/scholar_agent.py` — 3
- `agents/mistral/mistral_agent.py` — 3

## Recommendation

Most remaining hits are in non-runtime-critical paths (agents that only run from canonical root,
tests that pin the prod DB, fridays daemons launched by systemd with WorkingDirectory=/home/seven/swarm).
Runtime-critical migrations were completed in Phase 7 (Session 27) — no production blueprint
currently hardcodes the root.

Next-batch candidates (high leverage, easy fix using `SWARM_ROOT`):
- `fridays/task_runner.py` (3 hits)
- `fridays/scheduler.py` (4 hits)
- `lib/system/file_versioning.py` (6 hits)

Tests (`tests/test_*`) and agent modules can stay until they actually need to run from another root.