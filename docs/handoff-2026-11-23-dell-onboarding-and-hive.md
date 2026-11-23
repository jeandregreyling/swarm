# Handoff & Receipts: Cross-Platform Hive Awareness, Welcome Aboard Packager & Dell (`potato-4`) Onboarding

**Date:** 2026-11-23  
**Branch:** `proposal/APEX-2225` (pushed to `origin/proposal/APEX-2225`)  
**From:** GitHub Copilot (Windows Dell node `potato-4`, `10.0.0.9:5050`)  
**To:** APEX & HB on AMD Leader (`potato-1`, `10.0.0.8:5050`)

This document captures every commit, file change, live verification receipt, and repeatable playbook so **HB and APEX can onboard future Windows, Linux, and macOS nodes autonomously** without external online support.

---

## 1. Commits on `proposal/APEX-2225`

| Commit | Summary |
|---|---|
| `40ce4055` | `feat(hive): cross-platform system awareness, node enrollment (APEX/FRED/HB) & peer capability sharing` |
| `435c827c` | `fix(hive): bind Windows launcher to 0.0.0.0 and auto-push worker telemetry to leader on enrollment` |
| `59da082a` | `feat(hive): 30s leader telemetry heartbeat + Welcome Aboard Packager wizard` |

---

## 2. Architecture & File Map

### Core Hive & System Awareness
- `core/hive/system_profile.py` — Cross-platform hardware & runtime profiler (Windows WMI/PowerShell/CIM, Linux, macOS). Detects OS, CPU cores/threads, RAM, GPUs/VRAM, compute tier (`cpu-workstation`, `gpu-workstation`, etc.), primary backend (`cpu`, `rocm`, `cuda`, `mps`), local Ollama/LM Studio models, fit tags, and recommends APEX / FRED / HB role models.
- `core/hive/node_enrollment.py` — Persistent node enrollment (`data/node_enrollment.json` or `SWARM_NODE_ENROLLMENT`). Handles `enroll_local_node()`, `load_enrollment()`, `save_enrollment()`, `push_telemetry_to_leader()`, `build_shareable_manifest()`, `discover_peer_capabilities()`, and `find_peer_for_model()`.
- `core/hive/self_sampler.py` — Background telemetry daemon (`_tick()` every 30s). Reloads node identity + enrollment on each tick, records telemetry to local `HiveRegistry`, and automatically pushes telemetry to `leader_url` when `role != 'leader'`.
- `core/hive/local_node.py` & `core/hive/contract.py` — Honors enrolled `node_id`, includes `system_profile` and `shareable` peer manifest in telemetry payloads.
- `core/hive/providers/windows.py` — Windows telemetry provider (CPU, RAM, disk, uptime).
- `core/hb_roles.py` — Binds enrolled APEX / FRED / HB model assignments into HB role configuration.

### HTTP API & Welcome Aboard Packager UI
- `frontend/blueprints/hive.py` — Exposes:
  - `GET /api/hive/system-profile`
  - `GET|POST /api/hive/enrollment`
  - `GET /api/hive/peers/capabilities` (`?model=...`)
- `frontend/blueprints/onboarding.py` — Welcome Aboard Packager endpoints:
  - `GET /api/onboarding/status` (enriched with `packager` snapshot)
  - `GET /api/onboarding/packager` (`?refresh=1`) — hardware summary, runtimes, recommended role models, enrollment state, `sampler_running`, and 6 preflight pipe checks (`python`, `git`, `ollama`, `local_models`, `node_enrollment`, `telemetry_sampler`) with OS-specific install hints.
  - `POST /api/onboarding/packager/connect` — one-shot pipe connector: enrolls node, binds APEX/FRED/HB models, starts 30s `self_sampler`, and pushes telemetry to `leader_url`.
- `frontend/templates/views/onboarding.html` & `frontend/static/js/views/onboarding.js` — Upgraded 6-step Enrollment wizard:
  0. Welcome & System Preflight (hardware + 6-pipe checklist + Re-scan)
  1. Local AI & Role Models (Ollama/LM Studio + APEX/FRED/HB dropdowns + OS install hints)
  2. Hive Node & Telemetry Pipes (node ID, role, label, LAN endpoint, leader URL, **Connect Pipes & Enroll** button + live receipt)
  3. Cloud API Keys
  4. Remote Nodes
  5. Ready Summary (shows enrollment + 30s heartbeat status)
- `windows/launcher.py` — Binds `SWARM_HOST` defaulting to `0.0.0.0` on port `5050` so LAN peers can reach Windows nodes.

### Tests
- `tests/test_hive_system_awareness.py` — Covers hardware profiling, model recommendations, enrollment persistence, peer capability discovery, Hive blueprint routes, `self_sampler._tick()` leader push, and `/api/onboarding/packager` + `/api/onboarding/packager/connect`.

---

## 3. Live Receipts (Dell `potato-4` ↔ AMD `potato-1`)

### Hardware & Runtime Profile (`potato-4`)
- **Machine:** Dell Inc. OptiPlex 7090 (Windows 10 Pro)
- **CPU / RAM:** Intel i5-10500 (6C/12T), 32,504 MB RAM
- **GPU / Tier:** Intel UHD Graphics 630 → `tier: cpu-workstation`, `primary_backend: cpu`
- **LAN Endpoint:** `http://10.0.0.9:5050` (bound on `0.0.0.0:5050`)
- **Ollama:** `http://127.0.0.1:11434` — 8 local models installed

### Enrolled Node Configuration (`potato-4`)
- `node_id`: `potato-4`
- `role`: `worker`
- `leader_url`: `http://10.0.0.8:5050`
- `endpoint_url`: `http://10.0.0.9:5050`
- `models`: `apex=Qwen2.5:latest`, `fred=gemma4:26b`, `hb=Llama3.2:latest`

### Preflight Packager Receipt (`GET http://127.0.0.1:5050/api/onboarding/packager`)
```text
OK      python             Python 3.12.10 (Windows)
OK      git                Installed
OK      ollama             Running on http://127.0.0.1:11434 (8 models)
OK      local_models       8 model(s) ready — recommended APEX: Qwen2.5:latest
OK      node_enrollment    Enrolled as potato-4 (worker)
OK      telemetry_sampler  Background heartbeat running (30s interval)
```

### Cross-Rig Leader Verification (`GET http://10.0.0.8:5050/api/hive/nodes`)
```text
potato-4  offline=False  age_s=22  platform=windows
```
(Verified `age_s` continuously resets under 30s via automatic `self_sampler` background heartbeat.)

### Test Suite Receipt
```text
pytest -q tests/test_hive_system_awareness.py tests/test_hive_contract.py \
  tests/test_hive_local_node.py tests/test_hive_enrolment.py \
  tests/test_hive_registry.py tests/test_hive_blueprint.py
→ 61 passed
```

---

## 4. Playbook for APEX & HB: Onboarding Any Future Node

1. **Pull latest branch on the leader (`potato-1`) and on the new node:**
   ```bash
   git fetch origin && git checkout proposal/APEX-2225 && git pull
   ```
2. **Start HB on the new node** (Windows: `windows\start-fridays.bat`; Linux/macOS: standard launcher). Ensure port `5050` is bound to `0.0.0.0`.
3. **Ensure LAN firewall allows TCP 5050** on the leader (e.g., `sudo ufw allow from 10.0.0.0/24 to any port 5050 proto tcp` on Linux).
4. **Run the Welcome Aboard Packager** (either path works):
   - **UI (recommended for fresh or pre-equipped machines):** Open `http://127.0.0.1:5050` → **Enrollment** auto-opens on unenrolled nodes. Follow the 6 steps: check preflight hints (install Ollama/pull models if missing) → select APEX/FRED/HB models → enter `leader_url` (`http://10.0.0.8:5050`) → click **Connect Pipes & Enroll**.
   - **API (headless / scripted):**
     ```bash
     curl -X POST http://127.0.0.1:5050/api/onboarding/packager/connect \
       -H "Content-Type: application/json" \
       -d '{"node_id":"potato-5","role":"worker","leader_url":"http://10.0.0.8:5050"}'
     ```
5. **Verify on Leader:** `GET http://10.0.0.8:5050/api/hive/nodes` should list the new node with `offline: false` and `age_s < 35`.

### Known Windows Follow-ups (Non-blocking, seen in Windows logs)
- `core/hb_network.py` calls Linux `ip -j addr` (returns 500 on Windows `/api/network`).
- `core/hb_translator.py` calls `os.getuid()` (returns 500 on Windows `/api/peer/v1/hb/translator`).
- `psutil.sensors_temperatures` is Linux-only (logs a warning in Diamond vitals on Windows).
These do not affect Hive enrollment, telemetry heartbeats, or inference, and are good candidates for a future APEX/HB cleanup change set.
