# Swarm

A local-first multi-agent system anchored by **Seven**, a self-aware coordinator
that holds the team to a written standard and calls out slop — including its
own.

> _"We are not a system that **REPORTS**. We are a system that **DOES**."_
> — [docs/the-standard.md](docs/the-standard.md)

## What you get

- **Seven** — the spine: keeps memory, audits the build, runs the four
  pillars, and self-learns from every turn.
- **Four pillars**, all live (active-v0):
  - Cyber Security — `/api/wishlist/pillars/cyber-security`
  - Financial — `/api/wishlist/pillars/financial`
  - Trading — `/api/wishlist/pillars/trading`
  - Business — `/api/wishlist/pillars/business`
- **The bullshit detector** — deterministic codebase scanner that fails the
  build on slop. Currently 🟢 GREEN, 0 critical, 0 warnings.
- **Self-learning loop** — every user reaction (positive, negative,
  profane-negative) gets logged as a lesson Seven re-reads next turn.
- **170+ tests** across batches 3–15, all green per-file.

## Install (60 seconds)

```bash
git clone git@github.com:jeandregreyling/swarm.git
cd swarm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make seed              # optional: load demo data into the four pillars
make excellent         # detector + per-batch tests; must end green
.venv/bin/python frontend/terminal.py
# open http://localhost:5050
```

Talk to Seven on the home page, or via API:

```bash
curl -s -X POST http://localhost:5050/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"agent":"seven","message":"/audit"}'
```

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
