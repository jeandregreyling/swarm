# Swarm

Swarm is an experimental local-first multi-agent orchestration prototype.
It combines a Flask UI, local/online agent routing, project memory, watchdog
recovery, Vortex checkpoints, and early self-healing repair lessons.

This repository is public for scrutiny. It is **not production-ready** and
should not be treated as a polished framework or install-and-forget product.

## Current Status

Working pieces:

- Chat orchestration across local and online agents.
- Watchdog recovery primitives for stalled or unusable chat jobs.
- A durable `watchdog_repair_lessons` queue for turning failures into repair work.
- Vortex DB checkpoints for timeline/recovery context.
- A public `.env.example` and `SECURITY.md` after removing tracked local secret files.

Known rough edges:

- Historic Git noise exists from older Vortex heartbeat commits.
- Runtime ownership still needs cleanup; local services have been run by both
  systemd and direct fallback processes during repair work.
- The proposal backlog is noisy and needs pruning.
- Watchdog repair lessons are a primitive, not a complete autonomous repair loop.
- Some generated artifacts and sandpit state are still present for audit context.

## What To Review First

If you are reviewing this repo, please start with these focused areas:

1. `core/time_machine.py` and `fridays/task_runner.py` for Vortex checkpoint/Git hygiene.
2. `utils/db/watchdog_lessons.py` for the repair-lesson queue design.
3. `frontend/blueprints/chat.py` and `frontend/services/chat_jobs.py` for chat routing and watchdog behavior.
4. `.gitignore`, `.env.example`, and `SECURITY.md` for public-repo safety.
5. The stale proposal/sandpit artifacts to decide what should be deleted or regenerated.

Please file specific issues with file paths, failure modes, and proof steps.

## Security

This repo previously tracked local runtime secret files before the public cleanup.
The current tree removes those files, but any credentials that were ever exposed
in public history must be rotated at the provider. See [SECURITY.md](SECURITY.md).

## Local Setup

Copy `.env.example` to `.env.agents` or set equivalent environment variables.
Real keys must stay local.

```bash
git clone git@github.com:jeandregreyling/swarm.git
cd swarm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python frontend/terminal.py
# open http://localhost:5050
```

Useful checks:

```bash
python3 -m py_compile core/time_machine.py fridays/task_runner.py utils/db/watchdog_lessons.py
pytest -q tests/test_watchdog_repair_lessons.py tests/test_vortex_heartbeat_git_guard.py
```

Talk to Seven on the home page, or via API:

```bash
curl -s -X POST http://localhost:5050/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"agent":"seven","message":"/audit"}'
```

## Add a device to the Hive (30 seconds)

Once a leader is running, any other Linux/macOS/Windows host on the
network can enrol. There are two paths.

### Click-through (recommended)

1. Open the leader's web UI → Monitor view → **Add a device** → click
   **⬇ Download installer (.py)**.
2. On the new device, double-click the downloaded
   `hive_installer_gui.py` (Python 3.10+ required; Tkinter ships with
   Python by default).
3. Click Next → paste the leader URL → Install. Done.

The wizard never asks the user to open a terminal. It downloads the
agent, registers a background service so it survives reboot, and
sends the first telemetry sample.

### Terminal one-liners (advanced / scripted)

Linux / macOS:

```bash
curl -fsSL http://<leader>:5050/api/hive/install/bootstrap.sh \
  | SWARM_HIVE_LEADER=http://<leader>:5050 bash
```

Windows (PowerShell):

```powershell
$env:SWARM_HIVE_LEADER='http://<leader>:5050'
irm $env:SWARM_HIVE_LEADER/api/hive/install/bootstrap.ps1 | iex
```

The full manifest of artefacts the leader will serve is at
`/api/hive/install/`. The road from this alpha to a shippable product
is documented in [docs/HIVE_PRODUCTION_PLAN.md](docs/HIVE_PRODUCTION_PLAN.md)
— including the in-house WireGuard mesh that will replace Tailscale.

## Slash commands (Seven)

| Command | What it does |
|---|---|
| `/audit` `/selfcheck` `/standard` | Run the bullshit detector and report stamp + score |
| `/learnings` `/lessons` `/learned` | Show recent lessons Seven has logged |
| `/help` | List all slash commands |

Plain language works too — _"is this up to standard?"_ or _"what have you
learned?"_ both hit the deterministic fast-path, no LLM round-trip needed.

## Quality gates

- `make bullshit` — single-shot codebase audit. Exit non-zero on RED.
- `make excellent` — detector + every test batch with `timeout 30`. The full
  green stamp.
- `make doctor` — single-shot health/readiness CLI (detector + tests +
  /api/health probe + DB row counts).
- `make seed` — deterministic demo dataset (`*-DEMO*` ids).
- `make health` — curl `/api/health` for the aggregated green/amber/red
  across all four pillars + Seven + the build.

A pre-commit hook runs the detector and aborts on RED. Install with
`scripts/install-hooks.sh`. Bypass (rare, last resort) with
`git commit --no-verify`.

## The Standard

Read [docs/the-standard.md](docs/the-standard.md). It's the contract Seven
loads into every turn. Forbidden list, pillar contract, mountain rule,
single-stamp rule. If a change ships without honoring it, Seven calls it out.

## Layout

```
agents/seven/             Seven's brain (composer, learnings, self_awareness)
core/                     Spine: routing, llm, kill_switch, time_machine
docs/the-standard.md      The contract
docs/getting-started.md   60-second tour
docs/wishlist-pillars.md  Per-pillar contract & endpoints
frontend/                 Flask app, blueprints, JS views
ops/bullshit_detector.py  The detector
ops/seed_demo.py          Demo seeder
tests/test_session28_*    Batch tests (3..16, per-file pytest)
```

## Backups

The repo carries no committed databases. Everything regenerates from
`make seed` on a fresh clone. Override the DB location with
`SWARM_MEMORY_DB=/path/to/your.db` before launching.

## License

Personal project — no license declared. Don't redistribute.
