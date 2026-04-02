# SWARM COORDINATION MANIFEST
Generated: 2026-04-02 17:27

## Who Is Running
| Agent     | Role            | Can Initiate | Reports To |
|-----------|-----------------|:------------:|:----------:|
| gemma     | Director        | YES          | fridays    |
| qwen      | Analyst         | YES          | gemma      |
| llama     | Correspondent   | YES          | gemma      |
| eight     | SAP Specialist  | YES          | gemma      |
| duck      | Sanity Checker  | NO           | gemma      |
| sniffles  | Memory Auditor  | NO           | gemma      |
| librarian | Gatekeeper      | NO           | gemma      |
| fridays   | Orchestrator    | YES          | ghost      |

## Agent API Endpoints (Local, Port 5050)
- `POST /api/agent/tickets`         — Create a ticket/proposal
- `GET  /api/agent/tickets`         — My tickets
- `GET  /api/agent/proposals`       — All pending proposals (any status)
- `POST /api/agent/git/proposals`   — Create a Git ALM proposal (stage/unstage/commit)
- `GET  /api/agent/git/proposals`   — List my Git proposals (or all with `all_agents=1`)
- `POST /api/agent/git/proposals/INTERNAL-FRIDAYS-0379/execute` — Execute approved Git proposal

## Local Agents On Same Git-ALM Flow
- Included: gemma, qwen, llama, eight, duck, sniffles

## Communication Flow
1. Fridays heartbeat fires every 5 minutes
2. Fridays queries pending proposals
3. Fridays dispatches to correct agent or self-handles
4. Agent creates sub-proposals if more work is needed
5. Duck sanity-checks any closures

## Shared Files Convention
- `shared/COORDINATION.md`  — this file
- `shared/CURRENT_FOCUS.md` — what the swarm is working on right now
- `shared/BLOCKERS.md`      — anything blocking progress

## Escalation
If a local agent cannot resolve something, it creates a ticket tagged `escalate:paid`
and stops. The proposal stays `pending` until Ghost or a paid agent picks it up.
