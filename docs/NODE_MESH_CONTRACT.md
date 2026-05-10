# Node Mesh Contract v0 — Distributed Seven Peer Protocol

**Status:** Draft  
**Date:** 2026-05-10  
**Author:** agent-eighteen (P-308466EE76)  
**Project:** P-FE00C3A77C — POTATOFARM: Distributed Seven Mesh

## 1. Philosophy

Every device in the swarm is a **first-class Seven peer**. There is no "client/server" — there is only **master** (potato-1, the DELL Linux host) and **peers** (potato-2..N). The master is permanent and authoritative. Peers are autonomous but defer to the master for coordination.

Design rules:

1. **Local-first:** Every node must function fully offline with its own KB, agents, and inference.
2. **Capability-routed:** Work is dispatched to the node with the best matching capabilities, not to a fixed address.
3. **Git-synced KB:** The shared knowledge base travels via git. Each node pulls from origin on heartbeat. Changes are detected and auto-synced.
4. **Power-aware:** Mobile nodes (battery) deprioritize heavy jobs unless plugged in.
5. **Fail-forward:** If a node dies mid-job, the task retries on another matching node. No single point of failure except the master.

## 2. Identity Model

Each node has:

| Field | Description |
|-------|-------------|
| `node_id` | Stable identifier (e.g., `potato-2`, `linux-fc03ff3acb84e442`) |
| `role` | `master` or `peer`. Only one master per mesh. |
| `platform` | `linux`, `android`, `macos`, `windows`, `ios` |
| `user` | The logged-in Seven user on this node (`jeandre`, `ghost`, etc.) |
| `token` | Mesh auth token (JWT or opaque, minted by master at enrolment) |
| `capabilities` | Advertised capabilities (see §3) |
| `address` | Tailscale IP + port (e.g., `100.96.126.121:5050`) |

The master node is always `potato-1` (or whatever the operator names it). It never changes without explicit mesh reconfiguration.

## 3. Capability Advertisement v1

Capabilities are hierarchical strings. A node advertises what it **can do**, not what it **is**.

```
inference.cpu          — CPU-based inference (always)
inference.gpu          — GPU-accelerated inference (Vulkan/OpenGL/DirectML)
inference.npu          — NPU/DSP acceleration (NNAPI/CoreML/ANE)
inference.tflite       — TensorFlow Lite runtime available
inference.ollama       — Ollama server reachable
inference.coreml       — Apple CoreML available
inference.lmstudio     — LM Studio backend
scheduler.coordinator  — Can accept and route jobs from other nodes
scheduler.worker       — Can execute jobs dispatched by coordinator
storage.bulk           — Large local storage (>100GB free)
audio.capture          — Microphone access
audio.playback         — Speaker access
video.capture          — Camera access
sensors.location       — GPS available
sensors.imu            — Accelerometer/gyro available
```

**Compute tiers:** Capabilities can include a tier suffix for rough performance class:
- `.micro` — ~1-2 TOPS (older phone NPU)
- `.standard` — ~5-10 TOPS (modern phone NPU, M1)
- `.pro` — ~15-30 TOPS (desktop GPU, M2/M3)
- `.max` — ~50+ TOPS (datacenter GPU)

Example: `inference.npu.standard`, `inference.gpu.pro`

## 4. Discovery Protocol

### 4.1 Static Bootstrap (current)

Nodes are configured with the master's Tailscale IP at install time. No mDNS needed — Tailscale gives us Layer 3 connectivity already.

```
potato-2 bootstrap config:
  master: 100.87.66.45:5050
  self:   100.96.126.121:5050  (auto-detected from Tailscale)
```

### 4.2 Gossip Heartbeat

Every node POSTs a heartbeat to the master every 30 seconds (configurable):

```http
POST /api/mesh/heartbeat
Authorization: Bearer <mesh_token>
Content-Type: application/json

{
  "node_id": "potato-2",
  "user": "jeandre",
  "capabilities": ["inference.cpu", "inference.tflite", "inference.gpu", "inference.npu.standard"],
  "address": "100.96.126.121:5050",
  "telemetry": { /* full node.resource/v0 envelope */ },
  "git_head": "6138172",  // last known git commit
  "status": "healthy"     // healthy | busy | degraded | offline
}
```

The master responds with:
```json
{
  "ok": true,
  "mesh_nodes": [ /* full roster of all known nodes */ ],
  "git_behind": 3,         // how many commits behind origin
  "tasks_for_me": [ /* jobs this node should execute */ ]
}
```

### 4.3 Peer-to-Peer Fallback

If the master is unreachable, peers can query each other directly using the last known roster. The mesh degrades gracefully — no central SPOF for job execution, only for coordination.

## 5. Task Envelope Format

A task is a unit of work dispatched from one node to another.

```json
{
  "contract": "seven.task/v0",
  "task_id": "T-uuid",
  "origin_node": "potato-1",
  "target_node": null,           // null = router decides
  "required_capabilities": ["inference.npu.standard", "scheduler.worker"],
  "min_resources": {
    "ram_mb": 2048,
    "storage_mb": 500
  },
  "priority": "normal",          // low | normal | high | critical
  "payload": {
    "type": "tflite.inference",
    "model_url": "http://100.87.66.45:5050/models/mobilenet.tflite",
    "input_data": "base64...",
    "options": { "delegate": "nnapi" }
  },
  "timeout_seconds": 300,
  "max_retries": 2,
  "created_at": 1778377200
}
```

### 5.1 Task Lifecycle

```
PENDING → ASSIGNED → RUNNING → COMPLETED | FAILED | TIMEOUT
   ↑________|___________| (heartbeat from worker)
```

- **PENDING:** Router has received the task but not assigned it.
- **ASSIGNED:** Target node confirmed it can execute. Lease acquired.
- **RUNNING:** Target node reports progress via heartbeat.
- **COMPLETED:** Result posted back to origin or master.
- **FAILED:** Execution error. Retried on another node if retries remain.
- **TIMEOUT:** No heartbeat within `timeout_seconds`. Requeued.

### 5.2 Result Envelope

```json
{
  "contract": "seven.task_result/v0",
  "task_id": "T-uuid",
  "status": "completed",
  "node_id": "potato-2",
  "result": { /* task-specific output */ },
  "metrics": {
    "elapsed_ms": 15420,
    "ram_peak_mb": 1024,
    "power_mwh": 45
  },
  "completed_at": 1778379000
}
```

## 6. Security Model

### 6.1 Mesh Token

- Minted by the master at node enrolment.
- Revocable. Rotatable.
- Carried in `Authorization: Bearer <token>` header.
- Short-lived sessions (24h) with refresh.

### 6.2 Capability Sandbox

A node can **advertise** any capability, but the master validates it against telemetry. A node claiming `inference.npu` without `npu_present: true` in telemetry gets flagged and deprioritized.

### 6.3 Task Authorization

Before executing a task, the target node checks:
1. Token validity.
2. Task signature (HMAC with shared mesh secret).
3. Required capabilities match advertised capabilities.
4. Resource availability (RAM, storage, thermal headroom).

### 6.4 User Attribution

Every task carries the `user` field from the origin node. The target node logs who requested the work. This enables audit trails and billing/cost attribution across the mesh.

## 7. Git Sync Strategy

The shared KB is the git repo itself. Each node:

1. Polls `git fetch origin` every N minutes (or on heartbeat response).
2. If behind, fast-forwards (or stashes local changes, pulls, reapplies).
3. If local changes exist, commits and pushes (if configured).
4. Detects conflicts and surfaces them to the user.

**Critical files that must sync:**
- `core/knowledge/projects.py` — ALM DB schema
- `core/spine.py` — Event definitions
- `docs/` — All contracts and runbooks
- `agents/` — Agent definitions (read-only on peers)
- `tests/` — Test suite (for local validation)

**Files that should NOT sync:**
- `.env`, `nohup.out`, local logs
- Node-specific config (Tailscale IP, hardware profiles)
- Runtime state (PID files, sockets)

## 8. Failure Recovery

| Scenario | Behavior |
|----------|----------|
| Peer drops offline | Master marks stale after 2 missed heartbeats. Pending tasks requeued. Running tasks timeout and retry. |
| Master drops offline | Peers use last known roster. New jobs buffer locally. When master returns, buffered jobs are replayed. |
| Task fails on node A | Retry on node B with same capabilities. If no match, escalate to master for human decision. |
| Git conflict | Node stashes, pulls, attempts auto-merge. If conflict persists, surface to user and skip sync. |
| Battery low on mobile | Node auto-reports `status: degraded`. Master deprioritizes for heavy tasks. |

## 9. Potato Farm Dashboard

A new view (`/view-potato-farm`) that shows:

- **Topology map:** All nodes with their Tailscale IPs, platform icons, and health dots.
- **User pills:** Who is logged in on each node.
- **Capability matrix:** What each node can do, with tier badges.
- **Active tasks:** What's running where, with progress bars.
- **Task dispatch:** Drop a task envelope, click "Route", see which node picked it up.
- **Git sync status:** Which nodes are behind origin, which have local commits.
- **Power status:** Battery levels on mobile nodes.

## 10. Implementation Roadmap

| Phase | Deliverable | Owner |
|-------|------------|-------|
| 0 | This contract + `core/mesh/` module scaffold | agent-eighteen |
| 1 | Standalone Seven daemon (`sevend`) on Linux | agent-eighteen |
| 2 | Task router + capability matcher | agent-eighteen |
| 3 | Android Seven runtime (APK) | agent-eighteen |
| 4 | Mesh discovery + heartbeat protocol | agent-eighteen |
| 5 | Git sync daemon (`swarm-syncd`) | agent-eighteen |
| 6 | macOS, Windows, iOS packages | agent-eighteen |
| 7 | Potato Farm dashboard tile | agent-eighteen |

---

## Appendix A: Current Mesh State (2026-05-10)

| Node | Role | Platform | Tailscale IP | Capabilities | User |
|------|------|----------|-------------|--------------|------|
| potato-1 | master | linux-mint | 100.87.66.45 | cpu, ollama, coordinator, bulk | ghost |
| potato-2 | peer | android | 100.96.126.121 | cpu, tflite, gpu, npu.standard | — |
| potato-3 | planned | macos | 100.105.212.27 | — | — |
| potato-4 | planned | windows | TBD | — | — |
| potato-5 | planned | ios | 100.115.205.65 | — | — |
