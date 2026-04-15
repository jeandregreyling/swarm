# Seven's Swarm

A multi-agent AI orchestration platform that coordinates local LLM agents through
a shared governance layer, event bus, and federated discovery system.

Agents collaborate on research, tool building, code review, and knowledge management
through a proposal-driven workflow with full audit trails.

## Quick Start

```bash
git clone <repo-url> && cd swarm
bash scripts/install.sh          # checks deps, creates venv, generates .env
source .venv/bin/activate
python3 frontend/terminal.py     # starts on http://localhost:5050
```

Or step-by-step:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp examples/single-node.env .env   # edit with your paths
python3 frontend/terminal.py
```

## Features

- **13 Specialised Agents** — Gemma (coordinator), LLaMA (research), Qwen (code review),
  Phi-3 (QA), Scholar/Seeker (deep research), Ghost (planning), and more
- **Proposal Lifecycle (ALM)** — draft → submitted → approved → in_progress → done,
  with voting, delegation, and audit trails
- **Event Bus** — pub/sub message relay between agents with deduplication
- **Federated Multi-Node** — register nodes, sync proposals, share skills, relay events
- **Tool Builder** — agents can design, build, test, and deploy Python tools at runtime
- **Knowledge Base** — persistent memory, library, and cross-agent knowledge sharing
- **Research Engine** — multi-step research with internet access (Tavily) and citations
- **Web Terminal UI** — real-time chat, dashboards, theming, conversation management
- **Desktop Mode** — optional Tauri wrapper for native desktop deployment
- **Security** — rate limiting, HMAC key verification, input sanitisation, security headers
- **Observability** — structured JSON logging, `/api/metrics`, component-level health checks

## Architecture

```
┌─────────────────────────────────────────┐
│            Web Terminal UI              │
│  (HTML/CSS/JS · 30+ view modules)      │
├─────────────────────────────────────────┤
│       Flask Backend · 32 Blueprints     │
│    205+ API routes · REST + WebSocket   │
├──────────┬──────────┬───────────────────┤
│ Services │ EventBus │   Federation      │
│ (agents, │ (pub/sub │  (node discovery, │
│  tools,  │  dedup,  │   skill sharing,  │
│  research│  relay)  │   proposal sync)  │
├──────────┴──────────┴───────────────────┤
│        SQLite (WAL) · 75+ tables        │
└─────────────────────────────────────────┘
```

## Requirements

- Python 3.12+
- [Ollama](https://ollama.com) with at least `gemma3` and `llama3.2` models
- SQLite 3.35+ (ships with Python 3.12)
- Linux or macOS (Windows via WSL)

## Configuration

Copy an example environment file and edit it:

```bash
cp examples/single-node.env .env
```

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SWARM_ROOT` | *(required)* | Absolute path to repo root |
| `SWARM_ENV` | `production` | Environment: production / uat / dev |
| `SWARM_PORT` | `5050` | Web terminal port |
| `SWARM_SECRET_KEY` | *(required)* | Flask session secret |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |

See `examples/` for multi-node configurations.

## Running

**Single node (development):**
```bash
python3 frontend/terminal.py
```

**Production (systemd):**
```bash
sudo cp swarm-terminal.service /etc/systemd/system/
sudo systemctl enable --now swarm-terminal
```

**Desktop (Tauri):**
```bash
python3 scripts/desktop_launcher.py
```

## Testing

```bash
python3 -m pytest tests/ -v
```

Current baseline: 289+ tests across governance, research, tools, federation, and integration.

## Documentation

- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) — 205+ endpoint reference
- [docs/ARCHITECTURE_DIAGRAM.md](docs/ARCHITECTURE_DIAGRAM.md) — Mermaid architecture diagrams
- [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) — deployment and operations guide
- [docs/ALM_COOKBOOK.md](docs/ALM_COOKBOOK.md) — proposal lifecycle cookbook
- [docs/DEVELOPER_WORKFLOW.md](docs/DEVELOPER_WORKFLOW.md) — development workflow
- [docs/README.md](docs/README.md) — documentation hub

## Project Structure

```
swarm/
├── frontend/          # Flask app, static assets, Jinja templates
│   ├── blueprints/    # 32 route modules
│   ├── static/        # CSS, JS views, JS core
│   └── templates/     # HTML templates
├── agents/            # 13 agent configurations + skills loop
├── core/              # Pipeline, time machine, kill switch
├── utils/             # Database, security, caching, federation
│   └── db/            # Schema, migrations, domain modules
├── skills/            # Runtime-built agent tools
├── lib/               # Shared libraries
├── tests/             # pytest test suite
├── scripts/           # Installer, env generator, desktop launcher
├── examples/          # Example .env configurations
├── docs/              # Project documentation
└── ops/               # Operational scripts and runbooks
```

## License

Private — see repository for terms.
