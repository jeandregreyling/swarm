# Architecture — Seven's Swarm

**Last Updated:** 2026-04-22 | **Status:** Production, Post-Session 25 (gateway + pulse bus)

---

## Layer model

The runtime is organised in four tiers. Each tier owns a specific kind of
work; lower tiers never import higher tiers.

```
core/        ── pure engine: ollama gateway (core/llm.py), pipeline, time machine, kill switch
 services/   ── stateful helpers shared across blueprints (chat jobs, auth, queue wrappers)
  blueprints/ ── thin Flask route handlers; delegate to services
   static/js/ ── browser views; subscribe to /api/pulse and the other bus endpoints
```

- **core/llm.py** is the **only** module permitted to `import ollama` for chat
  or generation. It enforces finite `keep_alive`, per-model concurrency, and
  non-retrying stream behaviour. All agents and pipelines route through it.
- **`/api/pulse`** is the canonical live-metrics bus. Tiles subscribe to it
  instead of fanning out to multiple endpoints. Backed by a 3-second TTL cache
  inside `lib/system/monitor.get_system_status()`.

---

## System Overview

Seven's Swarm is a local, multi-agent AI deliberation system running on a single Dell OptiPlex 7090. Three distinct layers:

1. **Intelligence Layer** — Agent coordination, memory, debate pipeline
2. **Action Layer** — Fridays: Discord/Telegram bots, file/shell/browser agents, skills
3. **Presentation Layer** — Flask web terminal (port 5050)

All models load sequentially into a shared 33GB RAM pool with 48GB swap overflow. No parallelism. No GPU. CPU-only throughput ~1.4 tok/s for 8GB+ models.

---

## Entry Points

**Email (listener.py)**
IMAP poll every 60s. Classifies sender: SELF / NOTIFICATION / UNKNOWN / TRUSTED. Routes to queue_manager for intake.

**Telegram Bot (fridays/telegram_bot.py)**
Same pipeline as email. Supports: URGENT, NOTE, TAG, SNOOZE, TRUST DOMAIN, SKILL, SCHEDULE.

**Discord Bot (fridays/discord_bot.py)**
Same pipeline. 1900-char chunking. Button interactions: TRUST/NOTIFY/IGNORE, Force Close, Resend.

**Terminal (frontend/terminal.py, port 5050)**
Direct input from Ghost. Bypasses email queue. Same full ticket pipeline. SSE streaming for real-time agent updates.

---

## Queue & Ticket System

### queue_manager.py

```
intake()           — Add email to queue with system snapshot
mark_processing()  — Lock entry while being processed
mark_completed()   — Release entry, update queue positions
intake_internal()  — Agents add internal proposals
```

### ticket.py

```
create()           — Open ticket (conv_id, sender, subject, body, queue_id, priority)
librarian_close()  — Close after final answer, index to memory (importance 9)
get_ticket()       — Fetch full ticket detail
add_note()         — Agent contribution to ticket
```

### State Machine

```
WAITING (queued) → IN_PROGRESS (processing) → PENDING_CLOSURE → CLOSED (Librarian indexed)
```

---

## Agent Pipeline

### orchestrator.py — Two Stages

**Stage 1 — consult_stage1()**
1. Gemma reads question → FL-001 routing decision
2. If NEEDS_WEB: LLaMA searches DuckDuckGo
3. Result logged to ticket_notes

**Stage 2 — consult_stage2()**
1. Mistral reads LLaMA's note (if present)
2. Disagreement? → debate.py (2–3 rounds, Gemma judges)
3. Gemma synthesises final verdict
4. Verdict → memory_gemma → promote_to_verified (importance 9)

**Special FL-001 routes:**
- IS_SAP=yes → Route to Qwen3.6 or specialist
- IS_IDENTITY=yes → Librarian identity handler
- NEEDS_WEB=yes → Trigger LLaMA search

### Email Pipeline

```
Email arrives → classify_sender()
├─ SELF        → skip
├─ NOTIFICATION → silent file
├─ UNKNOWN     → pending_emails, ask Ghost (TRUST/NOTIFY/IGNORE)
└─ TRUSTED     → continue ↓

Librarian intake
  RAM/CPU check → strip noise → generate tags → assign TICKET-{id}
  ↓
ticket_create()  status: open
  ↓
Email 0 — Gemma read receipt (before any model loading)
  ↓
STAGE 1 — consult_stage1()
  Gemma routes → LLaMA searches (if NEEDS_WEB)
  Email 1: LLaMA answer + sources
  ↓
STAGE 2 — consult_stage2()
  Mistral reads LLaMA → debate if conflict → Gemma synthesises
  Verdict → memory_gemma → promote_to_verified
  Email 2: Gemma final verdict
  ↓
Librarian closes ticket
  Index to shared memory (importance 9) → ticket: closed
  ↓
Duck sanity check
  YES → quack logged, done
  NO  → flag_for_sniffles()
  ↓
Sniffles (if Duck flagged AND queue quiet 1h+)
  Audit all memory pools → PASS/WARN/FLAG
  FLAG → stop queue → notify Ghost
```

### Terminal Pipeline

```
Ghost types → skip queue → ticket_create() → spinner
→ STAGE 1 streams into Agent Panel 1
→ STAGE 2 streams into Agent Panels 2–3
→ Librarian close → Duck check → ticket closed
→ Results rendered in UI
```

---

## Memory System

### build_shared_context()

- Queries `memory` table for importance 9 entries
- Queries agent's personal pool (importance 5+)
- Sorts by importance DESC, created_at DESC
- Injects into agent system prompt as known facts
- No count limits — importance threshold only

### promote_to_verified()

Called by Librarian after ticket close. Indexes final Q&A to `memory` table with importance 9. Source='verdict'. Never archived.

### Importance Decay

- Importance 9: never archived (Gemma verdicts, Nine decisions)
- Importance 5: archived after 60 days
- Importance 3: minimum query threshold (30 days)
- Importance 1–2: excluded from all queries

---

## Debate System (debate.py)

Triggers when two agents disagree significantly.

**Round 1 (Challenge):** Mistral reads LLaMA's answer. Posts challenge.

**Round 2 (Defense):** LLaMA reads Mistral's challenge. Responds with evidence or concedes.

**Round 3 (Judgment):** Gemma reads both. Synthesises with evidence weighting. Result → memory_gemma.

---

## Audit Pipeline

**Duck (post-ticket-close, always):**
3–5 second sanity check. YES → quack logged. NO → flag_for_sniffles().

**Sniffles (queue quiet 1h+ or Duck flagged):**
Audits all memory pools. Checks: fabricated stats, self-serving entries, identity drift, API claims, contradictions with importance-9 facts.
Results: PASS / WARN / FLAG. FLAG stops queue entirely.

---

## Fridays Action Layer

### Skills (fridays/skills.py)

60+ skills: file read/write, browser automation, shell commands, scheduling. Each skill has permission gate (trust level check). Auto-creates work_proposals entry on system-write skills.

### File Agent (fridays/file_agent.py)

`read_sandpit()`, `write_sandpit()`, `read_shared()`, `list_sandpit()`. Enforces sandpit trust levels. All operations logged to `sandpit_log`.

### Shell Agent (fridays/shell_agent.py)

Whitelist-only command execution. Sudo escalation with approval token. All commands logged.

### Browser Agent (fridays/browser_agent.py)

Playwright headless browser. Navigate, screenshot, fill forms, extract text.

### Scheduler (fridays/scheduler.py)

`check_due()` loop every 60s. Supports: daily, weekly, monthly, hourly, interval. Action types: SHELL (subprocess), PYTHON (task_runner dispatch), URL (HTTP call).

### Task Runner (fridays/task_runner.py)

`@register` decorator for zero-boilerplate task definition. 13 registered tasks: housekeeping, archive, dedup, curate, digests, briefs, SLA checks, proposals, play time, knowledge seeding. All logged to `task_run_log`.

---

## Sequential Loading Strategy

On 33GB RAM, running two 5GB models simultaneously consumes 10GB real RAM. Sequential loading avoids thrashing entirely.

```
Gemma (4GB) loads → routes → unloads
LLaMA (2.3GB) loads → searches → unloads
Mistral (2GB) loads → analyzes → unloads
Gemma (4GB) loads → synthesises → unloads
Duck (tiny) loads → checks → unloads
Sniffles (7GB) loads (when idle) → audits → unloads
```

**keep_alive:** 300s (5 minutes) for all models. Auto-unload after 5 min inactivity.

**Throughput:**
- Gemma: ~3 tok/s
- LLaMA: ~2.5 tok/s
- Mistral: ~2 tok/s
- Sniffles: ~1.2 tok/s

---

## ALM Workflow

```
SKILL alm_create_proposal → work_proposals (status: pending)
  ↓
Duck auto-review (background, 1–3s)
  ↓ status: approved/rejected
Ghost approves in Studio
  ↓
SKILL alm_self_approve <id> → status: in_progress
  ↓
SKILL fs_patch / fs_write (actual changes)
  ↓
SKILL alm_complete <id> → status: done
  ↓
Duck quality check → status: uat
  ↓
Ghost marks executed → status: executed → PROD
```

**6-Stage Pipeline:**

| Stage | Status | Actor |
|-------|--------|-------|
| 1 | pending | newly created |
| 2 | approved | Duck reviewed |
| 3 | in_progress | agent working |
| 4 | done | agent finished |
| 5 | uat | Ghost/Duck reviewing |
| 6 | executed | shipped to prod |

---

## Database — 40+ Tables

### Core

```sql
agents           — Agent registry (21 enabled). Single source of truth for
                   number, label, display_label, model, tier, memory_table,
                   temperature, system_prompt, api_key_var, eta_seconds,
                   keep_alive. All runtime surfaces read via utils/db/registry.py
                   (60s TTL cache). Zero hardcoded agent lists in blueprints.
conversations    — Conversation log
messages         — Agent messages per conversation
```

### Memory Pools

```sql
memory           — Shared verified (importance 9 only)
memory_gemma     — Gemma verdict history
memory_llama     — LLaMA research notebook
memory_mistral   — Mistral analytical history
memory_qwen      — Qwen deep analysis notes
memory_nine      — Nine architect decisions
memory_ten       — Ten engineering reviews
memory_grok      — Eleven lateral thinking
memory_twelve    — Twelve temporal operations
memory_thirteen  — Thirteen SAP research
```

### Pipeline

```sql
queue            — Waiting emails/messages with system snapshot
tickets          — Full lifecycle (open → closed)
ticket_notes     — Agent contributions per ticket
chat_jobs        — Chat session state (survives server restart)
work_proposals   — Internal agent proposals for ALM pipeline
```

### Audit & Integrity

```sql
duck_log         — Every sanity check with result and timestamp
sniffer_log      — Every audit with full reasoning chain
sniffer_memory   — Sniffles pattern detection across audits
activity_log     — General swarm activity feed
file_versions    — File change tracking with before/after content
sandpit_log      — Every sandpit write (agent, file, hash)
```

### System

```sql
system_stats     — RAM, CPU, swap, active model snapshots
task_run_log     — Python task execution history
```

### Access Control

```sql
trusted_senders  — Full pipeline access
moderators       — Ghost level (receives all reports)
notification_senders — Silent filing
pending_emails   — Unknown senders awaiting Ghost approval
agent_access_levels  — Current trust level per agent
```

### Ghost Circle

```sql
ghost_circle     — Aggregated oversight (Ghost + Claude only)
claude_log       — Every Claude API call with token count
ghost_briefs     — Nine's synthesized intelligence reports
decisions        — Decision log (Vortex/Time Wizard)
time_machine     — Time-based system state snapshots
time_events      — Temporal event log
daily_checkpoint — Daily state captures
```

### Tasker & Scheduling

```sql
scheduled_tasks  — Task registry (SHELL/PYTHON action types)
task_run_log     — Python task execution with output
```

---

## Frontend Architecture

### Presentation — Single-Page App at /ui

Fridays dashboard with panels:
- Chat (multi-agent, streaming)
- Tickets (full lifecycle)
- Memory Browser (agent memory pools)
- Monitor (system health, RAM, CPU, swap, services)
- Studio (proposals, ALM, file explorer, Git)
- Docs / Knowledge Base
- Library (knowledge graph — force-directed canvas)
- Access (trusted senders)
- Vortex (time machine, decisions)

### Flask API Layer (frontend/terminal.py)

205+ routes across 32 blueprints. Key groups:
- `/api/chat/*` — Chat pipeline + job state
- `/api/tickets/*` — Ticket CRUD + notes
- `/api/memory/*` — Agent memory search
- `/api/queue/*` — Queue management
- `/api/work-proposals/*` — ALM proposal lifecycle
- `/api/skills/*` — Skill registry + execution
- `/api/tasker/*` — Scheduler + task runner
- `/api/kb/*` — Knowledge base CRUD
- `/api/monitor/*` — System health stats
- `/api/library/*` — Document library

SSE streaming at `/stream/<job_id>` for long-running operations.

### Theme Engine (theme_engine.py)

Time-of-day CSS injection. Color palettes: morning / afternoon / evening / night. Pure CSS custom properties — no re-renders. Persistent user overrides in localStorage.

---

## System Clock

All timestamps come from `utils/system_clock.py`. This is the single source of truth. No agent or service generates timestamps independently.

```python
from utils.system_clock import now, today, timestamp
ts = now()   # datetime object, local timezone
```

The Vortex tile (Twelve/Claude Haiku) uses system_clock for all decision logging and checkpoint creation.

---

## Security & Network

| Service | Port | Access |
|---------|------|--------|
| Ollama | 11434 | Tailscale only |
| Open WebUI | 3000 | Tailscale only |
| Fridays Terminal | 5050 | Tailscale only |
| DEV | 5051 | Ghost + Nine only |
| UAT | 5053 | Ghost only |

**API keys:** Stored in `/etc/environment` and `.env.agents`. Never in config.py. Rotated quarterly.

**Proposal gate:** Mutating actions (shell, file write, skill) blocked without valid `proposal_id` with status `executed`. All blocks logged to `activity_log`.

---

## Constraints & Invariants

1. Gemma routes first — no web search before reading question
2. Duck always runs — after every ticket close, no exceptions
3. Sniffles waits — 1h+ queue quiet before auditing
4. Librarian never speaks — tags only, no interpretation
5. Debate shows work — all reasoning visible to Gemma
6. Memory importance gates access — count limits forbidden
7. Proposals need approval — agents propose, Ghost approves
8. nvme0n1p1 untouchable — EFI boot partition
9. Timestamps centralised — all from system_clock.py
10. Ghost Circle private — Ghost + Claude only
