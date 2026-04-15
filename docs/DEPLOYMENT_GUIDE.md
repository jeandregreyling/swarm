# Deployment Guide — Seven's Swarm v4.0

## Prerequisites

- **Python 3.12+** (`python3 --version`)
- **Ollama** (for local AI agents) — https://ollama.com
- **Git** (for version control features)
- **SQLite 3.35+** (usually bundled with Python)

---

## Single-Node Setup

### 1. Clone & Install

```bash
git clone <repo-url> /opt/swarm
cd /opt/swarm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
# Generate template
python3 scripts/generate_env.py

# Edit .env with your values
cp .env.template .env
nano .env
```

**Required env vars:**
| Variable | Description | Default |
|----------|-------------|---------|
| `SWARM_ROOT` | Absolute path to swarm directory | (required) |
| `SWARM_ENV` | Environment: PROD, UAT, DEV | PROD |
| `SWARM_NAME` | Node name for federation | localhost |

**Optional env vars:**
| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_API_KEY` | API key for paid agents | (none) |
| `SWARM_RATE_LIMIT` | Requests/min rate limit | 60 |
| `SWARM_MAX_REQUEST_MB` | Max request body size | 1 |
| `SWARM_LOG_LEVEL` | Log level (DEBUG/INFO/WARN) | INFO |
| `SWARM_CORS_ORIGINS` | Allowed CORS origins | localhost |
| `SWARM_RELAY_TOPICS` | Events to relay cross-node | proposal.*,knowledge.new |

### 3. Initialize Database

The database auto-initializes on first run. Schema migrations run automatically.

### 4. Pull Ollama Models

```bash
# Required models
ollama pull gemma3:latest
ollama pull llama3.2:latest
ollama pull qwen2.5:latest
ollama pull phi3:latest
ollama pull mistral:latest
ollama pull deepseek-coder-v2:latest
```

### 5. Start the Server

```bash
# Development
source .env
python3 frontend/terminal.py

# Or use the launcher
python3 scripts/desktop_launcher.py --port 5050
```

### 6. Verify

```bash
curl http://localhost:5050/_health | python3 -m json.tool
```

---

## Systemd Services

### swarm-terminal.service (Main API)
```ini
[Unit]
Description=Seven's Swarm API Server
After=network.target ollama.service

[Service]
Type=simple
User=seven
WorkingDirectory=/opt/swarm
EnvironmentFile=/opt/swarm/.env
ExecStart=/opt/swarm/.venv/bin/python3 frontend/terminal.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### swarm-prewarm.service (Model Prewarming)
```ini
[Unit]
Description=Swarm Model Prewarm
After=ollama.service

[Service]
Type=oneshot
ExecStart=/opt/swarm/swarm-prewarm.sh
```

### Enable Services
```bash
sudo cp swarm-terminal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable swarm-terminal
sudo systemctl start swarm-terminal
```

---

## Multi-Node Setup

### Node Registration

On the **primary** node:
```bash
curl -X POST http://primary:5050/api/node/register \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "secondary-node",
    "url": "http://secondary:5050",
    "api_key": "generate-a-secure-key"
  }'
```

On the **secondary** node, register the primary:
```bash
curl -X POST http://secondary:5050/api/node/register \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "primary-node",
    "url": "http://primary:5050",
    "api_key": "primary-node-key"
  }'
```

### Federation Features

Once registered, nodes automatically:
- **Heartbeat**: Ping each other every 60s
- **Skill Sync**: Share skill registries
- **Event Relay**: Propagate bus events (proposals, knowledge)
- **Proposal Sync**: Cross-node proposal visibility

### Node Topology
```
                ┌─────────────┐
                │  PROD :5050  │
                │   (primary)  │
                └──┬───────┬──┘
                   │       │
          ┌────────┘       └────────┐
          │                         │
    ┌─────┴──────┐         ┌───────┴────┐
    │  UAT :5051  │         │  DEV :5052  │
    │ (secondary) │         │ (secondary) │
    └─────────────┘         └────────────┘
```

---

## Desktop Mode (Tauri)

### Prerequisites
- Rust toolchain (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- Tauri CLI (`cargo install tauri-cli`)

### Build
```bash
cd desktop
cargo tauri dev     # Development
cargo tauri build   # Production (creates .deb/.appimage/.msi)
```

### Headless Mode
```bash
python3 scripts/desktop_launcher.py --headless --port 5050
```

---

## Health Monitoring

### Health Endpoint
```bash
curl http://localhost:5050/_health
```
Returns component status: database, heartbeat, agents.

### Metrics Endpoint
```bash
curl http://localhost:5050/api/metrics
```
Returns: agents, proposals by status, bus events, node count, etc.

---

## Backup & Restore

### Database Backup
```bash
cp swarm_memory.db swarm_memory.db.backup.$(date +%Y%m%d)
```

### Time Wizard Checkpoints
```bash
curl -X POST http://localhost:5050/api/time/checkpoint/pre-upgrade
```

### Restore
```bash
curl -X POST http://localhost:5050/api/time/restore \
  -H 'Content-Type: application/json' \
  -d '{"checkpoint": "pre-upgrade"}'
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Address already in use` | Kill old process: `lsof -i :5050 \| awk 'NR>1{print $2}' \| xargs kill` |
| Blueprint load failures | Check `/_health` for details, install missing deps |
| Ollama connection refused | Ensure Ollama running: `systemctl status ollama` |
| 429 Rate Limited | Increase `SWARM_RATE_LIMIT` env var |
| Federation auth errors | Verify node API keys match on both sides |
| Database locked | Ensure WAL mode: `PRAGMA journal_mode=WAL` |
