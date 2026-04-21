# Seven's Swarm — Documentation

**Last Updated:** 2026-04-20

---

## Core Docs (Read These First)

| Doc | What it covers |
|-----|---------------|
| [PROJECT.md](PROJECT.md) | Vision, hardware, agent roster, memory design, phases, constraints |
| [AGENTS.md](AGENTS.md) | Every agent — model, role, capabilities, memory, personality, SKILL access |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, pipelines, database schema, ALM workflow, frontend |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | ALM workflow steps, environments, git, file versioning, UAT checklist, emergencies |

## Reference Docs

| Doc | What it covers |
|-----|---------------|
| [API_REFERENCE.md](API_REFERENCE.md) | 205+ routes across 32 blueprints |
| [FILE_STRUCTURE.md](FILE_STRUCTURE.md) | Directory layout |
| [BUGS.md](BUGS.md) | Active bug log |
| [FEATURES_TODO.md](FEATURES_TODO.md) | Planned features and roadmap |
| [CHANGELOG.md](CHANGELOG.md) | Full session history |

## Archive

Old docs that have been superseded are in [archive/](archive/). They are kept for historical reference only — do not update them.

---

## Filing Rules

- **Bugs go in BUGS.md** — include status (open/fixed/deferred)
- **Features go in FEATURES_TODO.md** — include phase and priority
- **Changes go in CHANGELOG.md** — include session number, agent, date
- **Architecture decisions go in ARCHITECTURE.md**
- **Agent changes go in AGENTS.md**
- **Workflow changes go in DEVELOPER_GUIDE.md**

When a doc diverges from the code, the code is wrong — fix the doc and fix the code together.
