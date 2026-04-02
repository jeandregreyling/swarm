# PROJECT.md — Seven's Swarm
*The Coder's bible. When this diverges from the code, the code is wrong.*
*Last updated: 2026-03-28 14:35:00 (Session 13 — Theme Architecture Refactor. See THEME_ARCHITECTURE_CHANGES.md)*

---

## 🔄 Recent Architectural Changes (28 March 2026)

**Theme Layer Separation Completed** — The Fridays web UI has been refactored to separate visual presentation from core terminal logic.

**What Changed:**
- ✅ Created `theme_engine.py` — Isolated theme management (colors, time-of-day, injection)
- ✅ Created `themes/fridays.json` — Central theme definition (4 time periods × color palettes)
- ✅ Created `templates/terminal_base.html` — Pure HTML/CSS rules (no hard-coded colors)
- ✅ Modified `terminal.py` — Now 2 lines changed (uses theme_engine instead of render_template)
- ✅ Refined UI — Time selection now smooth slider + "Set as Default" checkbox

**Impact:** Fridays theme is now a "looking glass" on top of stocky terminal. Can iterate colors/mood without touching core pipes.

**Details:** See [THEME_ARCHITECTURE_CHANGES.md](THEME_ARCHITECTURE_CHANGES.md)

---

## What We Are Building

### The Vision — Fridays

**Seven** is the brain. **Eight** is the specialist. **Fridays** gives them hands.

A fully local, autonomous, multi-agent AI swarm that does what OpenClaw does — but better, and free. OpenClaw is one model with tool wrappers. Fridays is a swarm of specialists that **deliberates before it acts**. Every action is debated, approved, executed, Duck-checked, and Sniffles-auditable. Nothing moves until the swarm agrees. No subscription. No cloud. No data leaving seven-potato unless the Ghost pushes it out.

**The difference that matters:** OpenClaw acts when one model decides. Fridays debates first. A single model deletes the wrong file. A swarm that votes before acting does not.

---

### The Three Layers

```
SEVEN     — Who they are. How they think. The brain.
            Gemma, LLaMA, Qwen, Librarian, Duck, Sniffles, Ghost.
            Memory pools, debate pipeline, FL-001 routing, Ghost Circle.

EIGHT     — What they know. The specialist layer.
            Eight = SAP HCM/ABAP. Ghost Layer specialists: Nine (Claude Sonnet 4.6), Ten (GPT-5.3-Codex), Eleven (Grok API), Twelve (Claude Haiku).
            Each specialist has own memory pool, uses Seven's infrastructure.

FRIDAYS   — What they can do. The action layer.
            Tools, sandpits, platform connectors, browser, shell, skills.
            Agents graduate from read-only → sandpit → system → full access.
```

---

### The Sandpit Model

Every agent gets two workspaces inside Fridays:

```
/home/seven/swarm/sandpits/
├── shared/      — all agents read + write. Collaboration layer.
├── gemma/       — Gemma's private workspace
├── llama/       — LLaMA's private workspace
├── qwen/        — Qwen's private workspace
├── eight/       — Eight's workspace (ABAP drafts, schema analyses, scenario working notes)
└── [ghost-layer]/ — Nine, Ten, Eleven, Twelve specialist workspaces
```

**Own sandpit** — private desk. Agents draft answers, write working files, store ABAP code, run experiments. Cannot affect the real system. Sniffles audits it.

**Shared sandpit** — the whiteboard. Gemma writes a plan, LLaMA does the research, Qwen adds analysis. The result sits in shared before anything moves to the real system. Duck checks anything that leaves shared.

**The trust ladder — agents graduate upward:**

| Level | Access | Approval needed |
|-------|--------|----------------|
| 0 — Observer | Read-only everywhere. Full system visibility, zero writes. | None |
| 1 — Sandpit | Write to own sandpit only. | None |
| 2 — Shared | Write to shared sandpit. | None |
| 3 — System write | Write to approved real paths. | Gemma approves each path |
| 4 — Shell | Execute from a whitelist of safe commands. | Ghost notified |
| 5 — Full | Unrestricted within Ghost-approved scope. | Ghost explicit sign-off |

**All agents start at Level 1.** They can see everything (Level 0 read access is always on). They earn higher levels through demonstrated reliable behaviour — Sniffles tracks error patterns, Duck tracks failure rates.

**Phase 6 elevation:** Gemma, LLaMA, Qwen, and Eight are elevated to Level 2 — shared sandpit write access — specifically to support the proposal system. Agents write to `sandpits/shared/proposals/` only. Sniffles audits every file before Ghost sees it.

Sniffles audits sandpit contents the same way it audits memory. Duck checks anything leaving a sandpit for the real system. Ghost Circle logs all real-system writes and shell executions.

---

### Phase 1 — Foundation (complete)
Email pipeline, memory pools, Duck, Sniffles, FL-001 routing, queue, tickets. The brain is built and running.

### Phase 2 — Interface (RL-012 to RL-016)
Terminal UI. Independent search per agent. Debate properly wired. Eight as SAP specialist. The swarm gets a face and gets smarter.

### Phase 3 — Fridays Action Layer (RL-017 to RL-021)
Sandpits created. Browser agent. File agent. Shell agent (sandboxed). Skills framework. Agents start at Level 1 and earn their way up.
- **RL-017 COMPLETE** — Sandpits. Directory structure + `sandpits.py` + `sandpit_log` DB table. Trust level enforcement (Level 0-5). Sniffles audits sandpits + memory. Terminal Sandpits view. Proposal system tested and working. Gemma/LLaMA/Qwen/Eight at Level 2, Nine at Level 3.
- **RL-017 COMPLETE** — Sandpits + Trust Ladder + Proposal System. Sniffles audits sandpits. Eleven (Grok API) seeded as Agent 11 (Ghost Layer).
- **RL-017 COMPLETE** — Sandpits + Trust Ladder + Proposal System. Sniffles audits sandpits. Eleven (Grok API) seeded as Agent 11 (Ghost Layer, Level 3).
- **RL-017 COMPLETE** — Sandpits + Trust Ladder + Proposal System. Eleven (Grok API) seeded as Agent 11 (Ghost Layer).

### Phase 4 — Platform Expansion (RL-022 to RL-025)
Telegram. Discord. WhatsApp. One swarm, many front doors. Same trusted sender model as email.

### Phase 5 — Specialist Agents (Eight onward)
Eight (SAP), Nine (Claude Sonnet 4.6 architecture), Ten (GPT-5.3-Codex engineering), Eleven (Grok API ideation), Twelve (Claude Haiku temporal governance). Each specialist has its own sandpit, memory pool, and role on top of Seven's infrastructure.

### Phase 6 — Agent Agency (RL-030 to RL-033) (In Progress)
Agents evolve from purely reactive to proactive. They can read KB docs, draft proposals, email Ghost, and collaborate via shared sandpit. Hands still off the real system — but minds are active between conversations.

---

### Phase 10 — Native Integration
Native desktop application wrapper for the Swarm Terminal. High-performance local operator surface.
---

**Eight** is the first specialist — an SAP HCM and ABAP expert built and taught by Ghost, a senior SAP Payroll Consultant. Eight is a thinking partner — the equivalent of a team of 20 consultants available at any hour to debate complex payroll scenarios, surface edge cases, and reason through configuration decisions. Eight uses Seven's infrastructure. Seven handles general knowledge. Eight handles SAP.

---

## Hardware

```
Dell OptiPlex 7090 | i5-10500 | 32GB RAM | Linux Mint 22.3
Hostname: seven-potato
User: seven

nvme1n1p1 — 469GB ext4 (15.8 Gb/s)
    / — OS, apps, swarm code
    ~/swarm/ — all Python files
    ~/swarm/swarm_memory.db — database

nvme0n1p3 — 232GB ext4 (31.6 Gb/s) — FAST DRIVE
    /mnt/swarm_drive/models/ — all Ollama models
    /mnt/swarm_drive/swap/ — 128GB swapfile (active)
    Effective memory: 32GB RAM + 128GB swap = 160GB

nvme0n1p1 — EFI (DO NOT TOUCH — EVER)
```

---

## The Agents

### The Ghost Layer

The Ghost Layer is the oversight, audit, and build layer of the swarm. **Only the Ghost Layer can authorise or execute real system changes.** Working agents propose and deliberate. The Ghost Layer approves, audits, and builds.

| Member | Identity | Role |
|--------|----------|------|
| Ghost | Human operator | Builds, approves, decides. Full system authority. Final word on everything. |
| Nine | Claude Sonnet 4.6 (Anthropic API) | System architect. Designs and builds the swarm. Session memory in memory_nine. Level 3 trust. |
| Ten | GPT-5.3-Codex (GitHub Models API) | Software Engineering Advisor. Provides code quality and clarity insights. Session memory in memory_ten. Level 3 trust. |
| Duck | qwen:1.5b (local) | Sanity checker. YES/NO quality gate after every ticket. Flags failures to Sniffles. |
| Sniffles | deepseek-r1:7b (local) | Memory and sandpit auditor. PASS/WARN/FLAG. Runs when queue is quiet. |

**Identity note:** Ghost's personal name is never used in agent context. Ghost is Ghost. If agents need to know who built the system, the answer is Ghost.

---

### Seven — Working Agents

| Agent | Model | Temp | Role |
|-------|-------|------|------|
| Gemma | gemma3:latest | 0.3 | Director — routes, synthesises, speaks last |
| LLaMA | llama3.2:latest | 0.6 | Correspondent — web search, fast first response |
| Qwen | qwen2.5:latest | 0.7 | Analyst — deep reasoning, debates, challenges |
| Librarian | qwen:latest | 0.1 | Gatekeeper — tags only, never speaks |

### Eight — SAP HCM / ABAP Specialist

Eight is a separate agent node built on top of Seven's infrastructure. It is not a general assistant — it is a senior SAP Payroll Consultant's thinking partner. Ghost teaches it. It learns permanently.

| Voice | Perspective | Role in debate |
|-------|------------|----------------|
| Eight-Functional | Payroll config, schemas, wage types, PCRs | First answer — standard functional approach |
| Eight-Technical | ABAP, BAPIs, user exits, enhancement points | Challenges — is the code actually doing what the config expects? |
| Eight-Devil | Edge cases, retro, EC/ECP gaps, timing issues | What could go wrong. What has been missed. |
| Eight-Gemma | Synthesis | Weighs the three voices, delivers the verdict |

**Eight's knowledge domains:**

| Domain | Detail |
|--------|--------|
| Wage types | Processing class, eval class, cumulation class, limits, indirect valuation, T512W |
| Schemas | ZM10/ZM04 structures, function calls, XDIVID, factoring, conditional branching |
| PCRs | Operations (ADDWT, MULTI, ELIMI, DIVID), table reads, IF/ELSE, retro rules |
| Config tables | T510, T511, T512W, V_512W_D, T7AU* (Australian-specific) |
| Infotypes | IT0008, IT0014, IT0015, IT0041, IT2001, IT2002, delimit logic, split indicators |
| EC/ECP | Replication model, delta handling, BTP iFlow, IDoc mapping, hire/rehire edge cases |
| ABAP | HR_PAY_WS_CALC_SALDO, READ_P0008, RPUCTP00, FM patterns, user exits, BADIs |
| Retro accounting | Trigger logic, WPBP split, cumulation delta, correction payroll runs |
| Time evaluation | Schema TM04, PT rules, quota generation, absence valuation |

**What Eight is NOT:**
- Not a magic pill — it knows what Ghost has taught it
- Not a replacement for Ghost — it's his thinking partner and sounding board
- Not connected to any SAP system — it reasons, it does not execute

**How Eight learns:**
1. Every scenario Ghost poses → answer → stored to memory_eight (importance 7-9)
2. Every correction Ghost makes → old memory flagged by Sniffles → new memory replaces it
3. Eight never makes the same mistake twice
4. Over time Eight learns Ghost's specific configuration, not just SAP standard

**Eight's model:** qwen2.5:latest (already running) — strong at technical reasoning and code generation. ABAP code generation uses qwen2.5 with an ABAP-specific context prompt.

---

## File Structure

```
/home/seven/swarm/
├── config.py              — All secrets and system prompts. NEVER SHARE.
├── database.py            — Complete database layer. 20+ tables. Run once to initialise.
├── listener.py            — Email loop. IMAP poll every 60s. Entry point.
├── orchestrator.py        — Agent pipeline. Gemma routes. Agents run. Gemma synthesises.
├── claude_api.py          — Ghost Circle advisor layer. Gemma calls Claude when stuck. Notifies Discord.
├── duck.py                — Sanity checker. YES/NO after every ticket.
├── sniffer.py             — Memory auditor. PASS/WARN/FLAG. Runs when queue is quiet.
├── queue_manager.py       — Librarian intake layer. Owns the queue table.
├── ticket.py              — Ticket lifecycle. create → close. Librarian owns close.
├── simulate.py            — Dry-run simulation. 3 fake tickets through full pipeline. No email.
├── terminal.py            — Swarm terminal web UI. Flask. Port 5050. (RL-012)
├── eight.py               — Eight agent. SAP HCM/ABAP specialist. Three-voice debate pipeline. (RL-013)
├── eight_memory.py        — Eight's knowledge loader. Seed and teach Eight. (RL-014)
├── internet.py            — LLaMA search. DuckDuckGo. Already wired.
├── internet_serper.py     — Gemma search. Google via Serper.dev. (RL-015)
├── internet_tavily.py     — Qwen + Eight search. Tavily AI search. (RL-015)
├── sandpits.py            — Sandpit filesystem layer. Trust level enforcement. sandpit_log. Sniffles-callable. (RL-017)
├── file_versioning.py     — Database-backed file version control with before/after content. (Phase A)
├── time_machine.py        — Point-in-time restore system with daily checkpoints. (Phase C)
├── vs_tools.py            — Ghost Layer architectural tools (Read/Write/Memory/Logs) for Nine. (Session 11)
├── app_launcher.py        — Native Desktop App (pywebview wrapper for port 5051). (Session 11)
├── swarm_tasks.py         — Scheduled tasks. SLA checks, snooze firing, daily digest, Tailscale cache, proposal scanner.
├── discord_notify.py      — Fire-and-forget Discord notification module. Pushes embeds to notification channel. (RL-023)
│
├── fridays/               — Fridays action layer. Agents' hands.
│   ├── file_agent.py      — File read/write with access level enforcement. (RL-018)
│   ├── browser_agent.py   — Playwright headless browser. (RL-018)
│   ├── shell_agent.py     — Sandboxed shell execution. Whitelist only. (RL-019)
│   ├── scheduler.py       — Task scheduling. Proactive agent behaviour. (RL-020)
│   ├── skills/            — Extensible skill modules. Auto-loaded. (RL-021)
│   ├── telegram_bot.py    — Telegram front door. Same trusted sender model. URGENT/NOTE/TAG/SNOOZE/TRUST DOMAIN. (RL-022)
│   ├── discord_bot.py     — Discord DM front door. Same pipeline as Telegram. Button interactions. (RL-023)
│   └── whatsapp_bot.py    — WhatsApp front door. (future)
│
├── templates/
│   └── terminal.html      — Dashboard UI. All views including KB editor, Monitor, Access.
│
└── sandpits/              — Agent workspaces. Created by RL-017.
    ├── shared/            — All agents read + write (Level 2)
    │   └── proposals/     — Agent-authored improvement proposals. Sniffles-audited before Ghost sees them.
    ├── gemma/             — Gemma's private workspace
    ├── llama/             — LLaMA's private workspace
    ├── qwen/              — Qwen's private workspace
    ├── eight/             — Eight's workspace (ABAP drafts, schema working notes)
    ├── librarian/         — Librarian's workspace
    └── sniffles/          — Sniffles' workspace (read-only — Level 0, no writes)

├── email_handler.py       — Gmail IMAP/SMTP.
├── email_cleaner.py       — Strip signatures, reply chains, prefixes. Subject prepended to question.
├── debate.py              — Three-round debate. Gemma judges.
├── housekeeping.py        — Daily cleanup. Archive low-importance memories.
├── monitor.py             — System stats daemon. get_system_status() + librarian_health_summary() callable by Librarian and terminal.
├── contradiction_check.py — Compare new agent memories against verified Gemma facts.
└── swarm_memory.db        — SQLite database. All memory lives here.
```

---

## Database — 25+ Tables

### Core
| Table | Purpose |
|-------|---------|
| agents | Agent registry — all 7 seeded on initialise |
| conversations | Conversation log |
| messages | All agent messages per conversation |

### Memory Pools
| Table | Purpose | Importance | Archived? |
|-------|---------|-----------|---------|
| memory | Shared verified pool — Gemma verdicts | 9 | Never |
| memory_llama | LLaMA personal notebook | 5 | Yes |
| memory_qwen | Qwen personal notebook | 5 | Yes |
| memory_gemma | Gemma verdict history — Sniffles reads this | 9 | Never |

### Pipeline
| Table | Purpose |
|-------|---------|
| queue | Waiting emails |
| tickets | Full ticket lifecycle |
| ticket_notes | Agent contributions per ticket |

### Integrity
| Table | Purpose |
|-------|---------|
| duck_log | Every sanity check with result and reason |
| sniffer_log | Every audit result with full chain of thought |
| sniffer_memory | Sniffles pattern detection across audits |

### Access Control
| Table | Purpose |
|-------|---------|
| trusted_senders | Full pipeline access |
| moderators | Ghost level — receives all reports |
| notification_senders | Silent filing, no response |
| pending_emails | Unknown senders awaiting Ghost approval |

### Ghost Circle
| Table | Purpose |
|-------|---------|
| ghost_circle | Aggregated visibility — Ghost and Claude only |
| claude_log | Every Claude advisory call with token count |

### System
| Table | Purpose |
|-------|---------|
| system_stats | RAM, CPU, swap, active model — written by monitor.py |

### Fridays
| Table | Purpose |
|-------|---------|
| sandpit_log | Every sandpit write — agent, file, timestamp, content hash. Sniffles audits this. |
| scheduled_tasks | Scheduled and recurring agent tasks |
| agent_access_levels | Current trust level per agent — starts at 1, Ghost grants higher |
| fridays_action_log | All Level 3+ real-system writes and Level 4+ shell executions |

### Platform / Access
| Table | Purpose |
|-------|---------|
| approval_tokens | Single-use UUID tokens for one-click email approval (RL-025) |
| snoozed_tickets | Active snoozes — ticket, wake time, fired flag |
| activity_log | Per-agent event log — used for idle detection and API usage stats |

### Knowledge Base
| Table | Purpose |
|-------|---------|
| project_docs | Ghost-authored KB docs that agents read during pipeline. Fields: doc_name, content, tags, created_at, updated_at. |

---

## Memory Design Principle

**Importance is the filter. Relevance is the gate. Time is the sort. Nothing else limits what an agent can see.**

Arbitrary count limits have been removed from all database query functions. Agents see everything relevant above their importance threshold. The database does not decide what matters — importance scores and query relevance do.

Importance scale:
- 9 — Gemma verified verdict. Permanent. Never archived. All agents read.
- 7 — Librarian indexed content. Significant but not verified.
- 5 — Agent personal memory. Working notes. Archived after 60 days.
- 3 — Minimum threshold for agent memory queries.
- 1-2 — Noise. Excluded from all queries.

---

## Pipeline Flow

### Email Pipeline

```
Email arrives at sevenpotato9@gmail.com
    │
    ▼ listener.py polls IMAP every 60 seconds
    │
    ▼ classify_sender()
    ├── SELF → skip
    ├── NOTIFICATION → file to Gmail label silently
    ├── UNKNOWN → save to pending_emails, ask Ghost to TRUST/NOTIFY/IGNORE
    └── TRUSTED / MODERATOR (non-command) → continue
    │
    ▼ RL-004: Librarian intake — queue_manager.intake()
    • Tags question, records system snapshot, assigns queue position
    │
    ▼ RL-005: ticket_create() — ticket opened
    │
    ▼ RL-006: Gemma read receipt — Email 0 (instant, before any model loads)
    │
    ▼ STAGE 1 — consult_stage1()
    • Gemma reads question — FL-001 routing (NEEDS_WEB / AGENTS / MODE / IS_IDENTITY / IS_SAP)
    • If NEEDS_WEB: LLaMA searches DuckDuckGo
    • Email 1 sent: LLaMA's fast answer
    │
    ▼ STAGE 2 — consult_stage2()  [RL-016: debate wired in here]
    • Qwen READS LLaMA's answer — reacts, challenges, or adds depth
    • If Qwen uses Brave Search for independent verification
    • If significant disagreement: debate.py fires (2-3 rounds, agents see each other)
    • If agreement or consult mode: Gemma synthesises
    • Gemma may use Tavily if authoritative source needed
    • Any agent may request a LLaMA search mid-reasoning (internal agent call)
    • Verdict → memory_gemma → promote_to_verified
    • Email 2 sent: Qwen + Gemma final verdict
    │
    ▼ RL-007: Librarian closes ticket — Duck check runs inside
    • Duck YES/NO sanity check
    • YES → ticket closed, logged to duck_log
    • NO  → flag_for_sniffles(), ticket still closes
    │
    ▼ RL-008: Random Sniffles trigger — 1-in-5 chance
    │
    ▼ SNIFFLES — when queue quiet 1+ hour OR Duck flagged
    • Audits all memory pools for unaudited entries
    • PASS / WARN / FLAG per entry
    • Emails Ghost if anything flagged
    │
    ▼ GHOST CIRCLE
    • Every Duck check, Sniffles FLAG, and Claude advisory call logged here
    • Ghost and Claude read this — agents do not
```

### Terminal Pipeline (RL-012)

```
Ghost types question in terminal UI
    │
    ▼ ticket_create() — ticket opened (queue skipped)
    │
    ▼ Spinner shown — "Swarm deliberating"
    │
    ▼ STAGE 1 — same consult_stage1()
    • LLaMA answer streams into Agent Panel 1
    │
    ▼ STAGE 2 — same consult_stage2() with debate
    • Qwen streams into Agent Panel 2
    • Debate transcript visible in UI if debate fires
    • Gemma streams into Agent Panel 3
    │
    ▼ Librarian closes ticket — Duck runs — same as email
    │
    ▼ FL-001 routing badge shown — which agents, which mode, which search engines used
```

### Eight Pipeline (RL-013)

```
Ghost asks SAP question (terminal or email)
    │
    ▼ Gemma FL-001: IS_SAP=yes → routes to eight.py
    │
    ▼ Eight-Functional answers — standard config/schema approach
    • Searches memory_eight first
    • If NEEDS_WEB: LLaMA searches SAP Notes / SCN / community
    │
    ▼ Eight-Technical reacts — ABAP, system behaviour, what the code actually does
    │
    ▼ Eight-Devil challenges — retro edge cases, EC/ECP timing, what was missed
    │
    ▼ Gemma synthesises across all three voices — final verdict
    │
    ▼ Answer + reasoning stored to memory_eight (importance 7-9)
    • Duck checks it
    • Sniffles audits it eventually
    • Wrong answer? Ghost corrects → old memory flagged → new memory replaces it
```

---

## Platform Channels — RL-022 / RL-023

### Telegram (RL-022) — Fridays bot
- Same full pipeline as email: trusted sender → queue → agents → reply
- Ticket numbers prefixed `TG-{conv_id}`. Answer includes `[Swarm #N]` reference.
- Commands: `URGENT` (keyword in message), `NOTE <text>`, `TAG <tag>`, `SNOOZE <Xh|Xd>`, `TRUST DOMAIN <domain>`, `SKILL <name>`, `SCHEDULE <spec>`
- Service: `swarm-telegram.service`

### Discord DM (RL-023) — Fridays bot
- Same pipeline as Telegram. Ticket numbers prefixed `DC-{conv_id}`.
- Message chunking at 1900 chars for Discord limit.
- Same commands as Telegram.
- Button interactions: TRUST/NOTIFY/IGNORE (from notification channel) and Force Close/Resend (from ticket embeds). Handled in `on_interaction` — `custom_id` format: `swarm:action:data`
- Service: `swarm-discord.service`

### Native Desktop App (Session 11)
- `app_launcher.py` uses `pywebview` to wrap the terminal UI in a native window.
- Runs on local port 5051 to avoid conflict with the systemd service on 5050.
- Supports `?app=1` flag for UI-specific desktop optimisations.

### Discord Notification Channel (RL-023)
- Channel ID: `1486232966379343894`
- Ghost's Discord user ID: `1486208449812365433` (trusted sender: `discord:1486208449812365433`)
- `discord_notify.py` — fire-and-forget module. Each notification spawns a throwaway `discord.Client` in a daemon thread, sends the embed, then dies.
- Events pushed to channel:
  - Unknown sender (+ TRUST/NOTIFY/IGNORE buttons)
  - Ticket opened / closed
  - SLA warning (>4h open)
  - Snooze fired
  - Daily digest
  - Ghost Circle (Claude advisory call)

**Colour constants:**
| Constant | Hex | Used for |
|----------|-----|---------|
| COLOUR_INFO | #4a90d9 | Ticket opened, Ghost Circle |
| COLOUR_OK | #43b581 | Ticket closed |
| COLOUR_WARN | #f0a500 | SLA warning, unknown sender |
| COLOUR_URGENT | #e53935 | URGENT tickets |
| COLOUR_GHOST | #00bcd4 | Ghost Circle / Claude advisory |

---

## Ghost Commands (email to sevenpotato9@gmail.com from moderator address)

| Command | Effect |
|---------|--------|
| TRUST email@address.com | Add to trusted senders, process any pending emails |
| NOTIFY email@address.com | Add to notification list — silent filing |
| IGNORE email@address.com | Same as NOTIFY |
| REMOVE email@address.com | Remove from trusted senders |
| REMOVENOTIFY email@address.com | Remove from notification list |

---

## Agent Internet Access — RL-015

Each agent has its own search engine. Three independent research paths. When all three find the same answer, confidence is high. When they diverge, debate fires.

| Agent | Engine | Library | API Key location | Notes |
|-------|--------|---------|---------|-----|
| LLaMA | DuckDuckGo | `duckduckgo_search` | None | Fast, broad, general web. `internet.py`. |
| Qwen | Tavily AI | `tavily-python` | `config.py` — TAVILY_API_KEY | AI-extracted content, clean summaries, source attribution. `internet_tavily.py`. |
| Gemma | Serper (Google) | `requests` | `config.py` — SERPER_API_KEY | Google results via Serper.dev — no subscription needed. `internet_serper.py`. |
| Eight | Tavily SAP-specific | `tavily-python` | `config.py` — TAVILY_API_KEY | Biased to SAP Help Portal, SCN, community. `internet_tavily.search_sap()`. |

Three independent research paths. Each agent's search results are labelled in context ([LLaMA / DuckDuckGo], [Gemma / Google], [Qwen / Tavily]) so agents know the source and can weigh credibility. When sources diverge, debate fires.

**routing.search_engines:** Routing dict now contains `search_engines: ['ddg', 'serper', 'tavily']` when web search runs. Terminal routing badges show each engine that fired.

**Setup:**
```bash
pip3 install tavily-python --break-system-packages
# Keys already in config.py:
# SERPER_API_KEY / SERPER_API_KEY_GENERIC
# TAVILY_API_KEY / TAVILY_API_KEY_GENERIC
# Both use Seven project key first, generic as fallback
```

---

## Ghost Circle — Claude API

`claude_api.py` is the Ghost Circle advisor layer.

**How it works:**
1. Gemma calls `check_if_already_solved(problem_type)` first
2. If a stored answer exists — use it, no API call
3. If not — call `ask_claude(problem_type, question, ticket_number)`
4. Claude receives full Ghost Circle context: recent events, Duck stats, Sniffles patterns, current ticket
5. Response stored to claude_log and memory_gemma
6. Mirrored to ghost_circle table

**Problem types Gemma uses:**
- `conflicting_agent_outputs` — LLaMA and Qwen disagree significantly
- `factual_uncertainty` — neither agent confident
- `identity_question` — question about the swarm itself
- `ethical_edge_case` — question Gemma isn't sure how to handle
- `routing_unclear` — FL-001 can't determine the right path
- `sap_escalation` — Eight's three voices all disagree, needs external arbitration
- `connection_test` — test the Ghost Circle connection

**Setup:**
```bash
export ANTHROPIC_API_KEY='sk-ant-...'
# Add to /etc/environment for persistence
python3 ~/swarm/claude_api.py  # test the connection
```

---

## Swarm Terminal — RL-012

A local web UI that replicates and exceeds Claude.ai's chat interface using the existing swarm architecture. No subscription. No single model. Multiple visible voices.

**What it does that Claude.ai cannot:**
- Multi-agent panel — LLaMA's answer arrives first, Qwen's analysis second, Gemma's verdict last
- FL-001 routing badge — shows which agents were used and why (web/agents/mode/identity)
- Kill switch per agent — disable any model in real time without restarting the swarm
- Memory browser — search all memory pools directly
- Ticket + Duck log — full audit trail of every question ever asked
- Direct terminal mode — bypasses email entirely, same pipeline, no IMAP

**Architecture:**
- `terminal.py` — Flask app, port 5050, behind Tailscale
- SSE (Server-Sent Events) for streaming — each agent streams as it responds
- Plain HTML/CSS/JS — no build step, no Node, no React
- Reads from `swarm_memory.db` — same DB as the email pipeline

**Routes:**
```
/                      → chat terminal (main interface)
/agents                → agent status + kill switches
/memory                → memory browser + search
/tickets               → ticket log with Duck verdicts and routing decisions
/api/kb                → Knowledge Base CRUD (list, get, create, update, delete)
/api/tickets/<n>/notes → Note CRUD per ticket (add, list, delete)
/approve/<action>/<token> → One-click email approval (RL-025)
```

**Dashboard views:**

| View | Contents |
|------|---------|
| Chat | Terminal chat interface, agent panels, routing badge |
| Tickets | Full ticket list with URGENT badge, note count pill, snooze indicator. Per-ticket notes with delete. |
| Memory | Memory pool search — sorted most recent first |
| Agents | Agent status + kill switches |
| System | RAM/CPU/swap gauges, disk usage, active model, memory pool counts |
| Sandpits | Per-agent file/byte counts with trust levels, recent sandpit_log |
| Access | Trusted/Notification/Domain columns. Add sender form with channel selector (email/telegram/discord). Channel badge on each entry. |
| Monitor | Live activity feed (SSE), service health dots (Listener/Telegram/Discord/Scheduler/Terminal) |
| Docs | Flow diagram, reference docs accordion, PROJECT.md render, Knowledge Base editor |

**Terminal pipeline vs email pipeline:**
```
Email:    queue_intake → ticket_create → Email 0 → Stage 1 → Stage 2 → librarian_close → send_reply
Terminal: (skip queue) → ticket_create → spinner   → Stage 1 → Stage 2 → librarian_close → render in UI
```

Duck still runs. Tickets still close. Memory still writes. Only email is skipped.

**Port:** 5050 — Tailscale only. Open WebUI stays on 3000.

---

## Tailscale — VPN

Ollama (port 11434), Open WebUI (port 3000), and Swarm Terminal (port 5050) are locked behind Tailscale. Only accessible from devices on the Tailscale network.

```bash
# Install on any new device
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Check connection
tailscale ip -4
```

Public internet cannot reach Ollama or Open WebUI.

---

## Python Dependencies

```bash
# Installed
pip3 install anthropic --break-system-packages
pip3 install psutil --break-system-packages
pip3 install duckduckgo_search --break-system-packages

# Needed before next build session
pip3 install flask --break-system-packages          # terminal.py (RL-012)
pip3 install tavily-python --break-system-packages  # internet_tavily.py (RL-015)
# Brave Search uses standard requests library — no extra install needed
```

**Environment variables** — add to `/etc/environment` then reboot or `source /etc/environment`:
```
TAVILY_API_KEY=tvly-...
BRAVE_API_KEY=BSA...
ANTHROPIC_API_KEY=sk-ant-...
```

All installed as the `seven` user so listener.py and terminal.py can import them.

---

## Initialise the Database

Run once. Safe to run again — IF NOT EXISTS throughout.

```bash
cd ~/swarm && python3 database.py
```

Expected output: 22 tables confirmed ready (includes sandpit_log, memory_eight).

---

## Start the Swarm

```bash
cd ~/swarm && python3 listener.py
```

Then send an email to sevenpotato9@gmail.com from a trusted address.

---

## Phase 6 — Agent Agency (RL-030+)

The agents evolve from purely reactive (answer when asked) to proactive (think between conversations, surface proposals). They still have **no hands on the real system** — but they have minds that run between conversations.

### The Model

```
IDLE (1hr no activity_log entries, excluding task-check events)
    │
    ▼ Agent play time triggers
    │
    ▼ Agent reads:
    •  Own memory pool
    •  Shared sandpit
    •  KB docs (project_docs)
    │
    ▼ Agent drafts a proposal
    •  What to improve
    •  Why
    •  What the impact would be
    │
    ▼ Writes to sandpits/shared/proposals/<agent>_<timestamp>.md
    │
    ▼ Sniffles audits the file (PASS/WARN/FLAG)
    │
    ▼ PASS → swarm_tasks proposal scanner picks it up
    │
    ▼ agent_email_ghost() sends email to Ghost + Discord notification
    │
    ▼ Ghost reviews in KB tab → Approve or Reject
    •  Approve → proposal imported to KB + agent memory updated
    •  Reject  → optional feedback written to agent sandpit
```

### Key Rules

- Agents can **read** everything at their trust level. No new permissions needed for reading.
- Agents can **write proposals** to `sandpits/shared/proposals/` only. No other shared writes during play time.
- Sniffles **must pass** a proposal before swarm_tasks delivers it. Flagged proposals are quarantined, not deleted — Ghost can still review them.
- Ghost **always decides** whether a proposal becomes real. Agents can suggest. Ghost approves.
- Proposals are **additive only**. Agents propose new KB docs, new system ideas, new skill ideas. They do not propose to delete or modify existing config.
- Play time runs at most **once per agent per 24 hours** — no agent spam.

### New Files (Phase 6)

| File | Purpose |
|------|---------|
| `agent_proposals.py` | Play time logic: idle detection, proposal drafting, Sniffles audit, write to shared/proposals/ |
| `agent_email_ghost.py` | Sends email + Discord notification when a proposal is ready for review |
| KB tab — Review Queue | Dashboard section in Docs tab showing pending proposals with Approve/Reject buttons |

### Idle Detection

```python
# Activity in last hour? Don't run.
# Check activity_log for non-task-check events in past 3600s
SELECT MAX(created_at) FROM activity_log
WHERE event_type != 'task_check'
AND created_at > datetime('now', '-1 hour')
# If result is None → agent is idle → play time fires
```

---

## Session Log

### Session 1 — 2026-03-19
- Fresh Linux Mint install (ext4)
- Ollama installed, models pulled: gemma3, llama3.2, qwen2.5, qwen
- Docker installed, Open WebUI running at localhost:3000

### Session 2 — 2026-03-19
- Python + SQLite memory layer built
- database.py, orchestrator.py, internet.py, email_handler.py, listener.py, debate.py
- First end-to-end email test successful

### Session 3 — 2026-03-20
- Email body stripping via email_cleaner.py
- Pending queue, two-stage email flow, agent-specific memory pools
- systemd services active, all agents seeded
- 128GB swap on fast NVMe — effective memory 160GB
- Sniffles first audit, Duck built and wired in
- FL-001 Gemma routing active

### Session 4 — 2026-03-24
- database.py rewritten: 20 tables, importance-based memory, no arbitrary count limits
- claude_api.py built: Ghost Circle advisor layer live
- anthropic, psutil, duckduckgo_search installed
- ARCHITECTURE.md written — full system reference
- Hardware confirmed: nvme1n1p1 (OS), nvme0n1p3 (fast drive + swap)

### Session 5 — 2026-03-24
- queue_manager.py + ticket.py wired in (RL-004, RL-005)
- listener.py rewritten: Librarian intake, Gemma read receipt (RL-006), Librarian close (RL-007), random Sniffles trigger (RL-008)
- simulate.py built: 3-ticket dry run, all passed Duck, DB writes confirmed
- DB schema migrations: 6 tables aligned to match injected database.py schema
- duck.py fixed: writes to duck_log, updates tickets.duck_result, reads own history for cheer rotation
- LLaMA/Qwen identity preamble removed from system prompts
- Subject now prepended to question body — agents have full context
- config.py deduplicated (was 3x copies of every prompt)
- Swarm Terminal (RL-012) designed and added to project plan
- Eight (RL-013/014) designed — SAP HCM/ABAP specialist with three-voice debate pipeline
- Independent agent search (RL-015) designed — Brave for Gemma, Tavily for Qwen/Eight, DDG stays for LLaMA
- Debate wiring (RL-016) designed — Qwen reads LLaMA before responding, disagreement triggers debate.py
- Internal agent calling designed — Qwen/Gemma can request LLaMA search mid-reasoning

### Session 6 — 2026-03-24
- **RL-012 COMPLETE** — Swarm Terminal live. Flask port 5050. SSE streaming. Kill switches. Memory/Tickets/Agents views.
- **RL-016 COMPLETE** — Debate wired into Stage 2. Qwen reads LLaMA before responding. Disagreement detection fires challenge round. Gemma judges with full debate context. Debate transcript streamed to terminal UI with ⚔ panels.
- **RL-013 COMPLETE** — Eight live. Three-voice pipeline: Functional/Technical/Devil's Advocate → Gemma synthesis. IS_SAP routing in FL-001 (Gemma + keyword fallback). LLaMA skipped when Eight handles. Status callbacks stream voice progress to terminal.
- **RL-014 COMPLETE** — eight_memory.py built. Seed/teach/correct/list modes. 5 foundational SAP knowledge entries seeded: processing classes, T510/T511/T512W, retro accounting, XDIVID factoring, EC/ECP architecture. memory_eight table live in DB.
- Terminal pipeline branching: IS_SAP → Eight path (4 model calls), standard → LLaMA+Qwen+Gemma path (3-5 calls)
- Debate R2 panels render with ⚔ divider in terminal. Eight voices render with ⚙ divider and teal colour scheme.
- All callers of consult_stage2 (listener.py, simulate.py) updated to unpack 3-tuple with debate metadata.
- SSE timeout raised to 900s (Eight pipeline can take 8-12 min on this hardware — 4 sequential model calls)

### Session 8 — 2026-03-24
- **RL-015 COMPLETE** — Independent agent search live. Three engines: LLaMA=DuckDuckGo (unchanged), Gemma=Serper/Google (`internet_serper.py`), Qwen=Tavily AI (`internet_tavily.py`), Eight=Tavily SAP-specific (`search_sap()`). Brave Search replaced by Serper (no subscription required). Keys in `config.py` — project Seven key + generic fallback for both Serper and Tavily. Web context now shows source labels per engine. Terminal routing badges updated: show DDG / Google / Tavily individually per engine that fired.
- Routing dict gains `search_engines` list — surfaces what actually ran to terminal and logs.

### Session 7 — 2026-03-24
- **RL-017 COMPLETE** — Sandpits live. `/home/seven/swarm/sandpits/{shared,gemma,llama,qwen,eight,librarian,sniffles}/` created. `sandpits.py` built: read/write/list/delete with trust level enforcement. Sniffles (Level 0) blocked from all writes. All operations logged to `sandpit_log` table (DB + schema updated).
- **Sniffles enhanced** — `sniffer.py` now audits all 5 memory pools (added memory_eight) + all sandpit files via `sandpits.get_all_sandpit_files()`. Sandpit audit uses separate `sniff_sandpit()` prompt focused on escape attempts and inappropriate content. Pattern tracking updated to cover all new sources.
- **Librarian system awareness** — `monitor.py` gains `get_system_status()` (live RAM/CPU/temp/disk/cores/memory pools/tickets) and `librarian_health_summary()` (plain-text summary callable by Librarian). Live read — never from DB cache.
- **Terminal System tab** — `/api/system` endpoint, `/api/sandpits` endpoint. System tab in terminal: RAM/CPU gauge bars with colour (green/amber/red), disk usage, active model, memory pool counts, consultation stats. Sandpits tab: per-agent file/byte counts with trust levels, recent sandpit_log operations table.
- **Ghost bubble CSS fix** — `.ghost-message` + `.ghost-bubble` styles added so conversation history renders correctly for messages from Ghost.

### Session 9 — 2026-03-25
- **Foundation UAT passed** — 6 bugs fixed, 3 missing wires reconnected. simulate.py 4/4. Live end-to-end verified.
- **Dashboard indicators** — URGENT badge, note count pill, snooze indicator on ticket list rows.
- **Note deletion** — Delete button on each note row in ticket detail panel.
- **Memory sort fixed** — All UNION branches in `_memory_search()` now sort `created_at DESC, importance DESC` (was `importance DESC` only — stale Eight memories dominated).
- **KB editor (RL-026)** — New section in Docs tab. Ghost creates/edits/deletes docs agents read during pipeline runs. `/api/kb` routes. `project_docs` table uses `doc_name` field.
- **`_load_api_key()`** — `claude_api.py` now parses `/etc/environment` directly as fallback when env var not in process environment (needed for systemd services).
- **Ghost Circle verified** — Claude API connection confirmed with $5 credit. Notifies Discord notification channel after each advisory call.
- **Discord bot (RL-023)** — `fridays/discord_bot.py` built. Full swarm pipeline for Discord DMs. `DC-{conv_id}` tickets. Same URGENT/NOTE/TAG/SNOOZE/TRUST DOMAIN commands as Telegram. Button interactions via `on_interaction` handler.
- **Discord notification channel (RL-023)** — `discord_notify.py` built. Fire-and-forget module. All swarm events push to channel `1486232966379343894`. TRUST/NOTIFY/IGNORE buttons on unknown sender embeds. Force Close/Resend buttons on ticket embeds. Button callbacks handled in `discord_bot.py` `on_interaction`.
- **Telegram parity** — `telegram_bot.py` updated: URGENT detection, NOTE/TAG/SNOOZE/TRUST DOMAIN commands, `[Swarm #N]` in Gemma verdict, priority passed to `ticket_create`.
- **swarm_tasks.py notifications** — SLA warning, snooze fired, daily digest all push to Discord notification channel.
- **listener.py notifications** — Unknown sender and ticket open/close events push to Discord notification channel.
- **Ghost Discord ID** — `discord:1486208449812365433` added as trusted sender.
- **Bugs fixed**: `priority` column (was in `queue` table, not `tickets`), `project_docs` column mismatch (`doc_name` not `title`), `/api/docs` route conflict fixed by renaming to `/api/kb`, Discord button callbacks (throwaway client → `on_interaction` dispatch), note popup JS error.

### Session 10 — 2026-03-25
- **PROJECT.md updated** — This document. Architecture, Phase 6, all new files/tables documented.
- **Phase 6 architecture designed** — Agent agency model: idle detection → play time → proposal → Sniffles audit → email Ghost → KB review queue → Approve/Reject.
- **Monitor tab enhancements** (in progress) — Swap/NVRAM display, API usage stats (Claude tokens from claude_log, Serper/Tavily call counts from activity_log), service health panel, Tailscale node list (cached).
- **Access tab** (in progress) — Discord/Telegram channel badges on sender list entries.
- **Sandpit Level 2 elevation** (in progress) — Gemma, LLaMA, Qwen, Eight elevated to Level 2. `proposals/` subfolder created.
- **Proposal system** (in progress) — `agent_proposals.py`, `agent_email_ghost()`, review queue in KB tab.

### Session 11 — 2026-03-26
- **Discord Bot Live** — `fridays/discord_bot.py` and `discord_notify.py` fully integrated.
- **Desktop App Built** — `app_launcher.py` created for native operator experience.
- **Logging Hardening** — Fixed `NameError` bugs in `orchestrator.py` and `listener.py` by properly initializing loggers.

---

## What Comes Next

### Done — Phase 2 (complete)
- ✅ **RL-012** — Swarm Terminal. Flask/SSE. Port 5050. Kill switches. Memory/Tickets/Agents/System/Sandpits views. Dark UI.
- ✅ **Session 11** — Native Desktop App wrapper (`app_launcher.py`).
- ✅ **RL-013** — Eight. Three-voice SAP specialist. Functional/Technical/Devil → Gemma synthesis. IS_SAP routing.
- ✅ **RL-014** — Eight knowledge loader. Seed/teach/correct/list modes. 5 foundational entries seeded.
- ✅ **RL-015** — Independent agent search. LLaMA=DDG, Gemma=Serper/Google, Qwen=Tavily, Eight=Tavily SAP.
- ✅ **RL-016** — Debate wired. Qwen reads LLaMA. Disagreement detection + challenge round. Gemma judges.

### Done — Phase B (System Clock)
- ✅ **B-1** — Visible System Clock in Fridays UI.
- ✅ **B-2** — All agents migrated to use `system_clock.py`.

### Done — Phase 3 (partial)
- ✅ **RL-017** — Sandpits. Directory structure + `sandpits.py` + `sandpit_log` DB table. Trust level enforcement. Sniffles audits. Terminal Sandpits view.
- ✅ **RL-017b** — Librarian system responder. `IS_SYSTEM` added to FL-001. `librarian_health_summary()` injected when routing detects system questions.
- ✅ **RL-017c** — Swarm awareness. `_swarm_awareness_block()` injected into every `build_shared_context()` call.
- ✅ **RL-010** — Simulation mode. `SIMULATE=true` env var intercepts all `send_reply` calls.
- ✅ **RL-021** — Skills framework. `fridays/skills/` auto-loaded. SKILL command in Telegram/Discord.
- ✅ **RL-020** — Scheduler. `SCHEDULE` command in Telegram/Discord. `scheduled_tasks` table.

### Done — Phase 4 (complete)
- ✅ **RL-022** — Telegram bot. Full pipeline. URGENT/NOTE/TAG/SNOOZE/TRUST DOMAIN. `[Swarm #N]` in verdict.
- ✅ **RL-023** — Discord DM bot. Full pipeline. Button interactions. Discord notification channel.
- ✅ **RL-025** — One-click email approval. TRUST/NOTIFY/IGNORE links in emails + Discord buttons.
- ✅ **RL-026** — KB editor in dashboard Docs tab. Ghost authors docs agents read during pipeline.

### Done — Phase A (File Versioning)
- ✅ **A-1** — Sudo Permission Toggle Flag.
- ✅ **A-2** — Nine's full `/swarm` write access.
- ✅ **A-3** — File Change Detection & Versioning (`file_versions` table, `track_file_change`).
- ✅ **A-4** — Document History + Diff Viewer in UI (basic "Changes" tab).

### Done — Phase D (UI/UX Improvements)
- ✅ **D-1** — VS → Studio Rename throughout interface.
- ✅ **D-2** — Fix CSS Layout (black gap issue).
- ✅ **D-3** — Build Terminal Window in Studio.

### In Progress — Phase 6 (Agent Agency)
- 🔄 **RL-030** — Monitor tab enhancements: swap/NVRAM display, API usage stats, service health, Tailscale cache.
- 🔄 **RL-031** — Access tab: Discord/Telegram channel badges on sender entries.
- 🔄 **RL-032** — Sandpit Level 2 elevation. `proposals/` subfolder in shared.
- 🔄 **RL-033** — Proposal system: idle detection, play time, Sniffles audit, `agent_email_ghost()`, review queue in KB tab.

### Backlog
- **RL-011** — Gmail Push Notifications (Google Cloud Pub/Sub, replaces 60s poll)
- **RL-018** — File + browser agent (`file_agent.py` + `browser_agent.py` with Playwright)
- **RL-019** — Shell agent (`shell_agent.py`, whitelist only, Level 4, Ghost notified)
- **RL-024** — WhatsApp bot (`whatsapp_bot.py`)
- **RL-027** — Nine (code specialist). Own sandpit. Uses Seven's infrastructure.
- **RL-028** — Monitor tab: API usage cost tracking (token × price per model)
- **RL-029** — Agent-to-agent direct messaging via shared sandpit channels

### Phase 5 — Specialist Agents (backlog)

**Eight (RL-013/014)** — SAP HCM/ABAP — live. See Eight section above.

**Future specialists:**
- Nine — code agent (Python, SQL, shell). Writes, tests, explains code.
- Ten — scheduling/calendar agent. Manages tasks, deadlines, reminders.
- Eleven — data agent. CSV, Excel, SQLite analysis. Talks to Qwen for interpretation.

Each specialist: own memory pool, own system prompt, uses Seven's infrastructure, audited by Sniffles, Duck-checked.

### Long Term
- Ghost Circle dashboard — read-only view inside terminal
- Mobile dashboard (PWA wrapper around terminal)
- Self-improvement loop — agents propose refinements to their own prompts via proposal system, Ghost approves

---

## Constraints That Must Never Be Broken

1. Librarian only receives content to tag — never questions, never raw email bodies
2. Sniffles never interrupts an active queue — waits for queue quiet 1+ hour
3. Duck runs after every ticket close, no exceptions
4. Claude never speaks directly to email senders — mentor not driver
5. Gemma routes FIRST — no web search before Gemma reads the question
6. IS_IDENTITY=yes only for swarm questions, agent names, and Ghost
7. nvme0n1p1 (EFI) is untouchable
8. OLLAMA_HOST=0.0.0.0 always
9. config.py is never shared or printed
10. The Librarian never speaks
11. Claude API is the last thing built — local pipeline must be stable first
12. Ghost Circle dashboard is read-only when built
13. Ollama port 11434 — Tailscale only
14. Agents propose, Ghost approves — no agent action ever reaches the real system without Ghost sign-off
15. Agent proposals must pass Sniffles audit before Ghost is notified — no raw agent output lands in Ghost's inbox
16. Play time fires at most once per agent per 24 hours — no agent spam
17. Open WebUI port 3000 — Tailscale only
18. Swarm Terminal port 5050 — Tailscale only
19. Terminal bypasses email but still creates tickets and runs Duck — the pipeline is never skipped
20. Eight is a thinking partner — it reasons and debates, it does not connect to or execute against any SAP system
21. Eight's knowledge is permanent — corrections replace memories, they do not delete history (Sniffles flags the old entry)
22. All agents start at Fridays Level 1 (own sandpit only) — they earn higher access through demonstrated reliability
23. Nothing leaves a sandpit for the real system without Duck checking it
24. All Level 3+ real-system writes and Level 4+ shell executions logged to ghost_circle
25. Skills and platform connectors follow the same trusted sender model as email — Ghost approves all new users/channels
26. Specialist agents (Eight, Nine, Ten...) always use Seven's infrastructure — no standalone pipelines
27. Sniffles audits sandpit_log with the same rules as memory pools
28. Claude API key in /etc/environment — never in config.py
29. Tailscale keys never stored in the swarm repository
30. Memory limits are set by importance threshold, never by count
31. All agents MUST date and time stamp (YYYY-MM-DD HH:MM:SS) their changes in documentation and use the file versioning system for all modifications.

---

## Known Issues

- Queue entries from crashed runs stay as `queued` forever — need a startup cleanup in listener.py (mark entries older than 2 hours as `abandoned` on boot)
- UTF-8 decode error on Windows-1252 encoded emails (byte 0x92) — email_handler.py needs latin-1 fallback

## Bug Log

### Fixed — Session 6

| ID | Description | Fix |
|----|-------------|-----|
| BUG-001 | Clicking past conversations showed title only — no messages loaded | Added `/api/conversations/<id>/messages` endpoint. `loadConversation()` now fetches and renders full history with Ghost bubbles + agent panels per message type |
| BUG-002 | Routing column in Tickets always showed `---` | `gemma_routing` never written to DB. Now saved as JSON after `consult_stage1()` returns in terminal pipeline |
| BUG-003 | Source (email vs terminal) not visible on conversation list items | Added 📧/🖥️ icon prefix to every conv-item. Border colour still present as secondary indicator |
| BUG-004 | Chat "falls over" after clicking a past conversation | `loadConversation()` now resets `isBusy` and closes any active EventSource before switching views |

### Fixed — Session 8

| ID | Description | Fix |
|----|-------------|-----|
| BUG-005 | Moderator emails that don't match a command fall through to the trusted-sender pipeline and get processed as questions | `process_emails()`: always `continue` after moderator block regardless of command match result |
| BUG-006 | Ghost's bare "NOTIFY" reply (no address) fails to match `startswith('NOTIFY ')` | `handle_moderator_command()`: extracts target email from subject `[Swarm] Unknown sender: addr`, expands bare NOTIFY/TRUST/IGNORE before matching. Requires `subject=subject` passed from `process_emails()` |
| BUG-007 | `'On '` in QUOTE_MARKERS too broad — questions starting with "On the topic of..." get truncated | Removed `'On '` from QUOTE_MARKERS. Added `_GMAIL_QUOTE_RE` regex (`^On .+ wrote:$`) — only matches actual Gmail quote headers |
| BUG-008 | `fetch_unread()` marks emails as read before processing — crash window silently drops emails | Removed `mail.store(\\Seen)` from `fetch_unread()`. Added `mark_as_read(msg_id)` to `email_handler.py`. Called in `process_emails()` only after each email is fully handled |
| BUG-009 | SAP emails in listener.py routed through Qwen/Gemma pipeline instead of Eight — `is_sap=True` in routing was never checked in `process_emails()` | Added `if routing.get('is_sap')` branch in listener.py and simulate.py. SAP path calls `consult_stage_eight()`, sends Eight's three voices + Gemma verdict. Email2 format updated for Eight output |
| BUG-010 | `add_trusted_sender()` used column name `note` but DB schema has `notes` — all TRUST commands silently failed | Fixed column name in database.py INSERT |
| BUG-011 | `get_pending_emails()` queried `created_at` but DB schema has `received_at` — TRUST processing crashed before emails were processed | Fixed column name in both SELECT queries |
| BUG-012 | `mark_pending_processed()` tried to set `resolved_at=datetime('now')` — column doesn't exist | Removed non-existent column from UPDATE |
| BUG-013 | `email_handler.py` crashed on emails with no Subject header — `decode_header(None)` raises TypeError | Added null-safe subject extraction: `raw_subject = msg['Subject'] or ''` |
| BUG-014 | Terminal chat path never called `queue_intake()` — terminal conversations got tickets but no queue entries, `queue_id=None` passed to `librarian_close` | Added `queue_intake()` call before ticket_create in terminal.py, queue_id now passed through |

---

*The Ghost speaks. The swarm thinks. The Librarian remembers.*
*The Duck checks. Sniffles watches. Claude advises when asked.*
*You can only do what you can do when you can do it.*
