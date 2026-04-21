# API Reference — Seven's Swarm v4.0
> Auto-documented from 205+ routes across 32 blueprints

## Base URL
```
http://localhost:5050
```

## Authentication
- **Node API Auth**: `X-Node-ID` + `X-Node-API-Key` headers
- **Shell Approval**: Token-based (`/approve/<action>/<token>`)

---

## System

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Root status check |
| GET | `/_health` | Detailed health with component status (DB, heartbeat, agents) |
| GET | `/ui` | Fridays UI (main HTML interface) |
| GET | `/library`, `/studio`, `/chat`, `/monitor` | UI redirects |

---

## Agents (`/api/agents`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/agents` | List all agents |
| GET | `/api/agents/status` | Agent status summary |
| GET | `/api/agents/config` | All agent configurations |
| GET | `/api/agents/config/<name>` | Agent config by name |
| POST | `/api/agents/bootstrap` | Bootstrap default agents |
| POST | `/api/agents/hot-swap` | Hot-swap agent model |
| POST | `/api/agents/import` | Import agent config |
| GET | `/api/agents/export-all` | Export all agent configs |
| GET | `/api/agents/<name>` | Single agent details |
| POST | `/api/agents/<name>/toggle` | Enable/disable agent |
| POST | `/api/agents/<name>/reset` | Reset agent to defaults |
| POST | `/api/agents/<name>/decommission` | Decommission agent |
| POST | `/api/agents/<name>/reactivate` | Reactivate agent |
| POST | `/api/agents/<name>/temperature` | Update temperature |
| GET | `/api/agents/<name>/export` | Export agent config |
| GET | `/api/agents/key/<name>` | Get agent API key var |
| GET | `/api/agents/capabilities` | Agent capabilities |
| GET | `/api/agents/capability-matrix` | Capability matrix |
| GET | `/api/agents/<agent>/memory` | Agent memory |
| POST | `/api/agents/<agent>/memory/write` | Write to agent memory |
| GET | `/api/agents/<agent>/skills` | Agent skills |
| GET | `/api/agents/memories/query` | Cross-agent memory query |

---

## Chat (`/api/chat`)

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/chat` | Send message (supports multi-agent, relay) |
| GET | `/api/chat/jobs/status` | Job queue status |
| POST | `/api/chat/jobs/cancel` | Cancel running job |
| POST | `/api/chat/librarian/review` | Librarian review |

---

## Conversations (`/api/conversations`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/conversations` | List conversations |
| GET | `/api/conversations/<id>` | Get conversation |
| GET | `/api/conversations/<id>/messages` | List messages |
| DELETE | `/api/conversations/<id>/messages/<msg_id>` | Delete message |
| GET | `/api/conversations/<id>/timeline` | Event timeline |

---

## Proposals (`/api/work-proposals`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/work-proposals` | List all proposals |
| GET | `/api/work-proposals/<id>` | Get proposal details |
| POST | `/api/queue` | Queue new proposal |
| PATCH | `/api/work-proposals/<id>/edit` | Edit proposal |
| DELETE | `/api/work-proposals/<id>` | Delete proposal |
| PATCH | `/api/work-proposals/<id>` | Update status (ALM transitions) |
| POST | `/api/work-proposals/<id>/duck-execute` | Execute via Duck agent |
| POST | `/api/work-proposals/<id>/agent-advance` | Agent auto-advance |
| GET | `/api/work-proposals/<id>/diff` | Git diff for proposal |
| POST | `/api/work-proposals/<id>/approve-to-uat` | Promote to UAT |
| POST | `/api/work-proposals/<id>/promote-to-prod` | Promote to PROD |
| POST | `/api/work-proposals/<id>/revert` | Revert proposal |
| GET | `/api/work-proposals/<id>/attachments` | List attachments |
| POST | `/api/work-proposals/<id>/attachments` | Upload attachment |
| GET | `/api/work-proposals/<id>/attachments/<att_id>` | Download attachment |
| DELETE | `/api/work-proposals/<id>/attachments/<att_id>` | Delete attachment |
| GET | `/api/work-proposals/<id>/notes` | List notes |
| POST | `/api/work-proposals/<id>/notes` | Add note |

---

## Agent Proposals & Governance

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/agent/proposals` | Agent's own proposals |
| POST | `/api/agent/claim` | Claim a pending proposal |
| GET | `/api/agent/capabilities` | Claim capabilities |
| POST | `/api/agent/think` | Agent thinking/planning |
| GET | `/api/agent/tickets` | Agent's tickets |
| GET | `/api/agent/identity` | Agent identity |
| GET | `/api/agent/git/proposals` | Git-linked proposals |
| POST | `/api/agent/git/proposals/<id>/execute` | Execute git proposal |
| GET | `/api/alm/status` | ALM lifecycle status |

---

## Federation (`/api/node`, `/api/federation`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/node/info` | This node's identity |
| POST | `/api/node/register` | Register remote node |
| GET | `/api/node/list` | List registered nodes |
| POST | `/api/node/discover` | Discover node by URL |
| POST | `/api/node/heartbeat` | Trigger heartbeat |
| GET | `/api/node/proposals` | Local proposals (auth required) |
| GET | `/api/node/skills` | This node's skills |
| POST | `/api/node/sync/proposals` | Sync proposals (auth) |
| POST | `/api/node/events` | Receive events (auth) |
| GET | `/api/federation/proposals` | Aggregated proposals (cached 30s) |
| GET | `/api/federation/roster` | Aggregated roster (cached 30s) |

---

## Research (`/api/research`)

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/research/start` | Start research session |
| GET | `/api/research/sessions` | List sessions |
| GET | `/api/research/<id>` | Session details |
| GET | `/api/research/<id>/evidence` | Session evidence |
| POST | `/api/research/<id>/resume` | Resume paused session |

---

## Tools (`/api/tools`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/tools/builds` | List tool builds |
| GET | `/api/tools/builds/<id>` | Build details |
| POST | `/api/tools/builds/<id>/validate` | Validate build |
| POST | `/api/tools/builds/<id>/test` | Test build |
| POST | `/api/tools/builds/<id>/register` | Register tool |
| GET | `/api/tools/templates` | Build templates |

---

## Tickets (`/api/tickets`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/tickets` | List tickets |
| GET | `/api/tickets/<number>` | Ticket details |
| POST | `/api/tickets/<number>/assign` | Assign ticket |
| POST | `/api/tickets/<number>/close` | Close ticket |
| POST | `/api/tickets/<number>/reopen` | Reopen ticket |
| POST | `/api/tickets/<number>/resend` | Resend ticket |
| POST | `/api/tickets/<number>/snooze` | Snooze ticket |
| GET | `/api/tickets/<number>/notes` | List notes |
| POST | `/api/tickets/<number>/notes` | Add note |
| DELETE | `/api/tickets/<number>/notes/<id>` | Delete note |

---

## Memory (`/api/memory`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/memory` | List memories |
| POST | `/api/memory` | Create memory |
| POST | `/api/memory/bulk` | Bulk operations |
| GET | `/api/memory/<id>` | Get memory |
| DELETE | `/api/memory/<id>` | Delete memory |
| POST | `/api/memory/<id>/assign` | Assign to agent |
| POST | `/api/memory/<id>/attach` | Attach file |

---

## Knowledge Base (`/api/kb`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/kb` | List documents |
| POST | `/api/kb` | Create document |
| GET | `/api/kb/<id>` | Get document |
| PUT | `/api/kb/<id>` | Update document |
| DELETE | `/api/kb/<id>` | Delete (soft) document |
| POST | `/api/kb/<id>/restore` | Restore deleted doc |
| GET | `/api/kb/<id>/versions` | Version history |
| POST | `/api/kb/seed-swarm-docs` | Seed from swarm_docs |

---

## Library (`/api/library`)

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/library/ingest` | Ingest URL content |
| POST | `/api/library/ingest-pdf` | Ingest PDF |
| GET | `/api/library/search` | Search library |
| GET | `/api/library/sources` | List sources |
| GET | `/api/library/sources/<id>` | Source details |
| POST | `/api/library/sources/<id>/reprocess` | Re-index source |
| GET | `/api/library/model-status` | Embedding model status |
| POST | `/api/library/pull-model` | Pull embedding model |
| POST | `/api/library/seed` | Seed built-in collection (`swarm`, `fridays`) |

---

## Tasker (`/api/tasker`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/tasker` | List all scheduled tasks |
| POST | `/api/tasker` | Create scheduled task |
| GET | `/api/tasker/<id>` | Get task details |
| PUT | `/api/tasker/<id>` | Update task |
| DELETE | `/api/tasker/<id>` | Delete task |
| POST | `/api/tasker/<id>/run` | Run task immediately |
| POST | `/api/tasker/<id>/toggle` | Enable/disable task |
| GET | `/api/tasker/registered` | List Python-registered tasks (task_runner.py) |
| GET | `/api/tasker/history` | Recent task execution log |
| POST | `/api/tasker/bootstrap` | Seed default scheduled tasks (7 presets) |

**Action Types**: `SHELL` (subprocess via shlex.split), `PYTHON` (task_runner.py dispatch), `URL` (HTTP call)

**Schedule Types**: `daily HH:MM`, `weekly DAY HH:MM`, `monthly DAY HH:MM`, `hourly :MM`, `interval Nm` (every N minutes)

---

## Shell & Terminal

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/shell/execute` | Execute shell command |
| GET | `/api/shell/stream` | Stream output |
| POST | `/api/shell/stream/stop` | Stop stream |
| GET | `/api/shell/agent-commands` | Agent command queue |
| POST | `/api/shell/agent-kill` | Kill agent process |
| GET | `/api/shell/approve/<token>` | Approve sudo command |
| POST | `/api/terminal/run` | Run terminal command |
| GET | `/api/terminal/stream` | Stream terminal output |
| POST | `/api/terminal/stream/stop` | Stop terminal stream |
| GET | `/api/terminal/shortcuts` | List shortcuts |
| POST | `/api/terminal/shortcuts` | Create shortcut |
| DELETE | `/api/terminal/shortcuts/<id>` | Delete shortcut |
| GET | `/api/terminal/sudo-whitelist` | Sudo whitelist |
| POST | `/api/terminal/sudo-whitelist` | Add to whitelist |
| DELETE | `/api/terminal/sudo-whitelist/<id>` | Remove from whitelist |

---

## Git (`/api/git`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/git/status` | Git status |
| GET | `/api/git/diff` | Git diff |
| POST | `/api/git/stage` | Stage files |
| POST | `/api/git/unstage` | Unstage files |
| POST | `/api/git/commit` | Commit with message |

---

## Observability

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/metrics` | Operational metrics (agents, proposals, bus, nodes) |
| GET | `/api/monitor` | Monitor overview |
| GET | `/api/monitor/stats` | Monitor statistics |
| GET | `/api/trace/<job_id>` | Trace a job |
| GET | `/api/trace/conversation/<id>` | Trace conversation |

---

## Time Wizard

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/time/bootstrap` | Bootstrap time session |
| GET | `/api/time/sessions` | List sessions |
| GET | `/api/time/timeline` | Full timeline |
| POST | `/api/time/checkpoint/<name>` | Create checkpoint |
| GET | `/api/time/checkpoints` | List checkpoints |
| POST | `/api/time/restore` | Restore checkpoint |
| POST | `/api/time/log-decision` | Log decision |
| GET | `/api/time/decision-history/<id>` | Decision history |
| GET | `/api/time/stats/<agent>` | Agent time stats |
| GET | `/api/timeline` | Combined timeline |
| GET | `/api/system/time` | System time |

---

## Other Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/activity` | Activity log |
| GET | `/api/activity/stream` | SSE activity stream |
| GET | `/api/brief` | Current brief |
| POST | `/api/brief/generate` | Generate brief |
| GET | `/api/brief/history` | Brief history |
| GET | `/api/bugs-md` | BUGS.md content |
| GET | `/api/project-md` | PROJECT.md content |
| GET | `/api/project-md/raw` | PROJECT.md raw |
| GET | `/api/testing-md` | TESTING.md content |
| POST | `/api/testing/run-simulation` | Run test simulation |
| GET | `/api/docs` | Documentation index |
| GET | `/api/docs/text/<filename>` | Doc file content |
| GET | `/docs/html/<filename>` | Doc as HTML |
| GET | `/docs/download/<filename>` | Download doc |
| POST | `/api/exec` | Execute code |
| POST | `/api/exec/write` | Write + execute |
| POST | `/api/hands/run` | Run hands task |
| GET | `/api/health` | Legacy health |
| GET | `/api/circuit-breaker` | Circuit breaker state |
| POST | `/api/circuit-breaker/<agent>/reset` | Reset breaker |
| GET | `/api/deferred` | Deferred items |
| DELETE | `/api/deferred/<id>` | Remove deferred item |
| GET | `/api/roles-skills` | Roles + skills mapping |
| GET | `/api/sandpits` | Sandpit directories |
| GET | `/api/senders` | Email sender list |
| GET | `/api/services` | Running services |
| POST | `/api/services/<id>/restart` | Restart service |
| GET | `/api/skills` | Skills registry |
| GET | `/api/skills/permissions` | Skill permissions |
| POST | `/api/skills/run` | Run skill |
| GET | `/api/studio` | Studio interface data |
| GET | `/api/swarm/globals` | Global config |
| GET | `/api/swarm/status` | Swarm status |
| GET | `/api/system` | System info |
| GET | `/api/tailscale` | Tailscale status |
| GET | `/api/workspace/dir` | Browse workspace |
| GET | `/api/workspace/file` | Read file |
| POST | `/api/workspace/replace/preview` | Preview replacement |
| POST | `/api/workspace/replace/apply` | Apply replacement |
| GET | `/api/workspace/search` | Search workspace |
| POST | `/api/code-ops/commit` | Commit code changes |
| POST | `/api/code-ops/format` | Format code |
| POST | `/api/code-ops/pylint` | Run pylint |
| POST | `/api/code-ops/pytest` | Run pytest |
| GET | `/api/ghost_circle` | Ghost circle status |
| GET | `/api/nine` | Nine agent interface |
| POST | `/api/nine/actions` | Nine actions |
| GET | `/api/nine/history` | Nine history |
| GET | `/api/nine/stream` | Nine stream |
| GET | `/api/debates` | List debates |
| POST | `/api/debates/quick` | Quick debate |
| GET | `/api/debates/<id>/turns` | Debate turns |
| POST | `/api/debates/<id>/run` | Run debate round |
| GET | `/api/decisions` | List decisions |
| GET | `/api/decisions/<id>` | Decision details |
| GET | `/api/auth/context` | Auth context |
| GET | `/api/auth/profiles` | User profiles |
| GET | `/api/auth/profiles/<username>` | User profile |
| POST | `/api/killswitch/emergency` | Emergency kill |
| POST | `/api/killswitch/pause` | Pause system |
| POST | `/api/killswitch/resume` | Resume system |
| POST | `/api/killswitch/restart` | Restart services |
| GET | `/api/killswitch/buttons` | Kill switch buttons |
| POST | `/api/killswitch/agent/<name>/reset` | Reset agent |
| POST | `/api/localai/ollama/chat` | Ollama chat |
| GET | `/api/localai/ollama/models` | Ollama models |
| POST | `/api/localai/lmstudio/chat` | LM Studio chat |
| GET | `/api/localai/available-models` | Available models |
| GET | `/api/localai/status` | Local AI status |
| GET | `/api/ollama/models` | Ollama model list |
| GET | `/api/ollama/ps` | Ollama processes |
| POST | `/api/ollama/load` | Load model |
| POST | `/api/ollama/unload` | Unload model |
| GET | `/api/email/inbox` | Email inbox |
| GET | `/api/email/stats` | Email stats |
| GET | `/api/email/live` | Live email feed |
| GET | `/api/email/thread/<number>` | Email thread |
| GET | `/stream/<number>` | SSE ticket stream |
| GET | `/approve/<action>/<token>` | Token approval page |
