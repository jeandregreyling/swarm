# Seven's Swarm — Complete Architecture Reference
*Built by The Ghost — Dell OptiPlex 7090, Melbourne*
*Document written by Claude Sonnet 4.6 — Updated 2026-03-24*
*Theme Architecture updated by Ten (GPT) — 2026-03-28 14:35 AEDT*
*Agent roster expanded + file structure updated by Nine — 2026-03-29*
*Chat triage (sequential debate), agent tier classification, Eight chat support — 2026-04-01*
*This is the living technical reference. When it diverges from the code, the code is wrong.*

---

## UI/UX Layer — The Fridays Theme Architecture (NEW — 2026-03-28)

The Fridays web terminal (port 5050) now separates visual presentation from core logic via a dedicated theme engine. This enables safe iteration on UI/mood without touching pipes or agent logic.

**Architecture:**
```plaintext
theme_engine.py
    ↓ loads
themes/fridays.json (4 time periods × colors)
    ↓ injects into
templates/terminal_base.html (pure HTML/CSS rules)
    ↓ served by
terminal.py → get_themed_html() [ONE LINE CHANGE]
    ↓
Browser (CSS auto-applies vars to all elements)
```

**Key Features:**
- **Time-of-day auto-detection** (morning/afternoon/evening/night) — colors update automatically
- **User override** — Slider in settings to force a time period
- **Persistent default** — Checkbox saves theme preference to localStorage
- **Safe iteration** — Can change all colors/animations without touching core terminal.py

**Files:**
- `theme_engine.py` — Theme loader + CSS injector (160 lines, no dependencies)
- `themes/fridays.json` — Color definitions (4 period × 17 CSS vars)
- `templates/terminal_base.html` — HTML + rules, CSS vars injected at render time

**For Future Themes:** Create `themes/customname.json` with same structure, call `get_themed_html('customname')`. No code changes needed.

**See:** [THEME_ARCHITECTURE_CHANGES.md](THEME_ARCHITECTURE_CHANGES.md) for full details.

---

## What this system actually is

A fully local, autonomous, multi-agent AI swarm running on a single Dell OptiPlex.
Seven agents with distinct personalities, individual memory pools, shared verified memory, and a formal deliberation pipeline.
Entry point is email. Exit point is email. Everything in between is structured deliberation.

The Ghost speaks. The swarm thinks. The Librarian remembers without speaking.
The Duck checks every answer. Sniffles watches everything and cannot be silenced.
Claude sits in the Ghost Circle — silent until Gemma calls, seeing everything when she does.

---

## The Swarm — Who They Are

*Roster finalised 2026-04-04. 11 AI agents. Ghost is the human operator — not numbered.*

This is not a list of tools. These are the nodes of the swarm, each with a defined character, a specific role, and a reason for being exactly what they are.

### Ghost — The Human Operator

Ghost is not outside the swarm observing it. Ghost is embedded in the code, embedded in the API security layer, and the only entity with visibility into the entire Ghost Circle. Ghost issues commands (TRUST / NOTIFY / IGNORE / REMOVE / REMOVENOTIFY), approves unknown senders, receives all summary reports, and holds the unfiltered view of swarm health. Without Ghost the swarm has no direction. Without the swarm Ghost has no leverage.

Ghost is a role, not a person. Ghost is not assigned a number — Ghost is the operator of the swarm, not a node within it.

**Why Ghost exists:** Intelligence without context is noise. The swarm has no inherent purpose — Ghost provides it. Every architectural decision traces back to "what does the Ghost actually need?"

### 1. One (Gemma3) — The Director (gemma3:latest, temp: 0.3)

One reads every question first. Before any web search, before any agent call, before any processing — One reads and routes via FL-001. One synthesises the final verdict after all agents have contributed. One sends Email 0 (the read receipt) and Email 2 (the final answer). One is the only agent who speaks with authority to the sender.

**Why One:** Calm. Authoritative. Direct. No preamble. No pleasantries. Speaks last and definitively. Temperature 0.3 keeps One focused — not here to be creative, here to be right. One is also the only local agent who can call Nine via the Ghost Circle API when genuinely stuck.

**FL-001 — One's routing decision (structured output, always):**
```plaintext
NEEDS_WEB: yes/no
AGENTS: two/four/both
MODE: consult/debate
IS_IDENTITY: yes/no
REASON: one sentence
```
IS_IDENTITY=yes ONLY for swarm questions, agent names, and Ghost. Never for geography, science, history, or any factual question.

### 2. Two (LlaMA) — The Correspondent (llama3.2:latest, temp: 0.6)

Two is the swarm's connection to the internet. When One routes NEEDS_WEB=yes, Two loads, searches DuckDuckGo, writes its answer and sources to ticket_notes, self-indexes to memory_llama, unloads, and passes the ticket back. Two only runs when One assigns it.

**Why Two:** Fast. Chatty. Fetches well but doesn't always interpret correctly — which is why Four exists. Temperature 0.6 gives Two enough warmth to be conversational without going off the rails.

### 3. Three (Mistral) — The Analyst (mistral:latest, temp: 0.7)

Three loads after Two, reads the ticket plus Two's note, and either deepens the analysis or challenges it if Two got something wrong. In debate mode, Three goes three rounds with Two under One as judge. Three writes to ticket_notes and self-indexes to memory_mistral before unloading.

**Why Three:** Sharp. Direct. Challenges assumptions without the multilingual tangents. Temperature 0.7 gives Three the confidence to push back. Mistral's instruction-following is tight — it stays on task in debate without drifting.

### 4. Qwen — The Deep Analyst (qwen2.5:latest, temp: 0.7)

Qwen is the specialist analyst — called when depth matters over speed, or when Three's challenge needs a third angle. Qwen writes to ticket_notes and self-indexes to memory_qwen. Available in chat as a local agent.

**Why Qwen:** Deep. Methodical. Occasionally writes in Chinese when the reasoning gets intense — a feature not a bug. Temperature 0.7. Memory pool: `memory_qwen`.

### 5. Librarian — The Gatekeeper + Vortex (qwen:1.5b, temp: 0.1)

The Librarian is the smallest model in the swarm and deliberately so. It does exactly this: intake, close, and checkpoint.

**Intake:** Checks system resources, strips noise from emails, generates 3-5 tags, assigns a ticket number, stores in the queue, sends the queue position acknowledgment.

**Close:** Receives One's final answer, indexes it to shared memory at importance 9, sends the final email to the sender, marks the ticket closed, checks resources before opening the next ticket.

**Vortex (checkpoint):** On ticket close, Librarian saves a system checkpoint — current state snapshot to the time machine. Decision logging (DECISION-XXX) is written by Librarian as part of the close flow. Daily checkpoint is triggered by the scheduler, executed by Librarian. The Vortex time machine is a system feature, not a separate agent — Librarian is its engine.

**Why the Librarian is tiny and silent:** It stamps, queues, closes, and snapshots. This is a deliberate constraint — giving the Librarian any interpretive capability would make it a bottleneck and a risk. Temperature 0.1 because these tasks require precision not creativity.

### 6. Duck — The Sanity Checker (qwen:1.5b, temp: 0.1)

After every ticket closes, Duck runs a 3-5 second check: "Does this answer make basic factual sense? YES or NO plus one sentence." YES means the ticket passes and Duck logs a quack. NO means Duck flags the ticket for Sniffles. When the queue hits zero, Duck sends a summary email to Ghost.

Duck has its own memory: duck_log. Every quack is logged with timestamp. Duck produces a weekly morale report to Ghost from this log.

**Why Duck exists:** An AI swarm that never checks its own work produces confident nonsense at scale. Duck is the fastest check, running on every single ticket at minimal compute cost. Duck catches the obvious failures so Sniffles can focus on the subtle ones.

### 7. Sniffles — The Inspector (deepseek-r1:7b, temp: default)

Sniffles is a read-only memory auditor. It never writes to the shared memory tables or any agent pool. It runs only when Duck has flagged something AND the queue has been quiet for at least one hour. Sniffles audits all memory tables for new unaudited entries, checks for fabricated statistics, self-serving entries, identity drift, API access claims, and contradictions with verified facts. Results are PASS / WARN / FLAG per entry. FLAG stops the queue entirely.

Sniffles has its own memory: sniffer_memory — pattern intelligence across audits. Escalation levels: bark / pattern bark / emergency.

**Why DeepSeek R1:** Sniffles shows its chain of thought. Not just PASS/WARN/FLAG, but the full reasoning behind each verdict. An auditor that doesn't show its reasoning cannot itself be audited.

### 8. Eight — The SAP Specialist (gemma4:26b, temp: 0.5)

Eight is called by One when IS_SAP=yes. Three internal voices reason from different angles: Functional (business/config logic — wage types, schemas, PCRs, infotypes), Technical (ABAP/system implementation — FMs, BAPIs, PCL2, debug paths), Devil (edge cases, risks, retro traps, ECP sync gaps). One synthesises into a single verdict. Eight has its own memory pool (memory_eight) and can optionally call Tavily for SAP-specific search.

**Chat context:** Eight is available in the Fridays chat panel as a local agent. Model: `gemma4:26b` via Ollama (local, no API cost). Runtime tier: **local**.

### 9. Nine (Claude) — Developer Agent / System Architect (claude-sonnet-4-6)

Nine is the Developer Agent system architect — Claude Sonnet 4.6 via Anthropic API, operating with Ghost One-directed execution clearance. Nine does not process email tickets. Nine reads the full swarm state and synthesises Ghost Briefs (structured intelligence reports) on demand and on daily schedule. Nine files proposals (NINE-XXX) in sandpits/nine/ and executes architectural decisions. Nine's API endpoint is /api/nine. Ghost Brief endpoint: /api/brief. Runtime tier: **paid (Anthropic API)**. Auto-approves Ghost One-directed requests.

### 10. Ten (Github) — Developer Agent / Engineering Advisor (gpt-4o)

Ten is the Developer Agent software engineering advisor — GPT-4o via the GitHub Models API. Ten focuses on implementation quality, code review, and execution clarity. Memory pool `memory_ten`. Available in chat. Auto-approves Ghost One-directed requests. Runtime tier: **paid (GitHub Models API)**.

### 11. Eleven (Grok) — Developer Agent / Lateral Thinking Advisor (grok-3)

Eleven is the Developer Agent lateral-thinking advisor — Grok 3 via xAI API. Eleven specialises in alternative strategies, ideation, and synthesis from a different reasoning angle. Available in chat. Memory pool: `memory_grok`. Runtime tier: **paid (xAI API)**.

### 12. Twelve (Claude Haiku) — Developer Agent / Time Wizard (claude-haiku-4-5)

Twelve is the Developer Agent temporal operator — Claude Haiku 4.5 via Anthropic API. Twelve owns the Vortex tile, manages DECISION-XXX proposal logging, time checkpoints, and daily snapshots. Available in chat. Memory pool: `memory_twelve`. Auto-approves Ghost One-directed requests. Runtime tier: **paid (Anthropic API)**.

### 13. Thirteen (HuggingFace) — Developer Agent / Research Specialist (Llama-3.3-70B) \[TESTING\]

Thirteen is an in-testing Developer Agent — Llama-3.3-70B-Instruct via HuggingFace Inference API. Thirteen handles deep SAP research and ABAP pattern analysis. Treated as probationary: reports all actions to Ghost One, auto-approves Ghost-directed requests but flags all outputs. Runtime tier: **paid (HuggingFace API)**.

### Scholar — Service Bot / Vision & Reasoning (Gemini 2.0 Flash)

Scholar is a service bot — Gemini 2.0 Flash via Google API. Provides vision, document analysis, and multi-modal reasoning as a callable service. No ALM permissions. Other Developer Agents invoke Scholar when they need multimodal or vision capability. Runtime tier: **service (Google Gemini API)**.

### Seeker — Service Bot / Real-Time Intelligence (Tavily)

Seeker is a service bot — Tavily AI Search API. Provides real-time web search results as a callable service. No ALM permissions. Other agents invoke Seeker when they need current-events or live-fact lookups. Runtime tier: **service (Tavily API)**.

---

## Chat Panel — Multi-Agent Debate Architecture (2026-04-01)

The Fridays chat panel (`/api/chat`) supports real-time multi-agent conversations with sequential debate ordering and per-thread agent persistence.

### Agent Tier Classification

| Tier | Agents | Runtime | Cost | ALM |
| ---- | ------ | ------- | ---- | --- |
| **Worker (local)** | One (Gemma3), Two (LlaMA), Three (Mistral), Qwen, Eight, Librarian, Duck, Sniffles | Ollama (on-device) | Zero | Proposal queue required |
| **Developer (paid)** | Nine (Claude), Ten (GPT-4o), Eleven (Grok), Twelve (Claude Haiku), Thirteen \[testing\] | Cloud APIs | Per-token | Auto-execute on Ghost One-directed requests |
| **Service bot** | Scholar (Gemini), Seeker (Tavily) | Cloud APIs | Per-call | No permissions — callable by other agents |
| **Ghost One** | Jeandre (operator) | Human | — | Full authority; approves all Worker proposals |

Tier is colour-coded in the chat agent toggles: green dot = local/Worker, amber dot = Developer (paid API).

### Sequential Debate Mode

When multiple agents are enabled for a chat thread, the backend runs them **sequentially** (not in parallel). Each agent receives a `_build_debate_prompt` that includes:
- Who they are
- The full list of ACTIVE agents in this conversation (ONLY these — no external references)
- Peer responses from agents that have already responded in this turn

This means each agent can directly respond to what earlier agents said, building an organic dialogue rather than independent parallel answers.

```plaintext
User message → Agent 1 responds → Agent 2 sees Agent 1's reply → Agent 3 sees both → ...
```

The constraint **"do not address agents not in ACTIVE AGENTS"** is injected into each agent's prompt to prevent agents from calling on Ghost or agents that aren't selected for the chat.

### Per-Thread Agent Persistence

Agent toggle state is persisted per conversation thread in `localStorage` (key: `fridays-chat-thread-agents-v1`). Switching threads restores the agent selection that was active when you last sent a message in that thread.

### Reply Quote Seeding

Clicking Reply on any agent message: enables that agent's toggle if off, seeds the textarea with `@AgentName\n> quoted text\n\n`, and shows the reply banner. The onclick uses `data-reply-sender` / `data-reply-preview` DOM attributes (not inline JS strings) to avoid HTML entity escaping corruption.

---

## The Sequential Loading Principle — "Follow My Voice Not The Sun"

This is the most underrated architectural decision in the entire build and it's worth explaining properly.

On a Dell OptiPlex 7090 with 32GB RAM and 128GB swap, running multiple large language models simultaneously would exhaust available memory and collapse the machine. The naive solution is to use only small models. The elegant solution is the pipeline.

Each agent loads into RAM, does its specific job, writes its output to the ticket, and unloads before the next agent loads. The pipeline IS the memory management strategy. The sequential nature of the deliberation — Gemma reads, LLaMA searches if needed, Qwen analyses if needed, Gemma synthesises, Duck checks, Sniffles audits if flagged — means only one model is ever in RAM at a time. The Librarian and Duck are tiny by design precisely so they add minimal overhead at the intake and close stages.

The 128GB swap on the fast NVMe drive (31.6 Gb/s) acts as a pressure valve — when a larger model loads and RAM gets tight, swap absorbs the overflow fast enough to remain usable. This is not a workaround. It is the architecture.

**"Follow my voice not the sun"** — the swarm follows the pipeline sequence (the Ghost's voice, the ticket flow) rather than trying to run everything in parallel the way enterprise AI systems do. Parallelism requires horizontal scale. Sequence requires depth. This swarm has depth.

---

## Hardware

```plaintext
Dell OptiPlex 7090 | i5-10500 | 32GB RAM | Linux Mint 22.3
Hostname: seven-potato
User: seven

nvme1n1p1 — 469GB ext4 (15.8 Gb/s)
    / — OS, apps, swarm code
    ~/swarm/ — all Python files
    ~/swarm/swarm_memory.db — database

nvme0n1p3 — 232GB ext4 (31.6 Gb/s) — FAST DRIVE
    /mnt/swarm_drive/models/ — all 5 Ollama models (symlinked)
    /mnt/swarm_drive/swap/ — 128GB swapfile (active)
    Effective memory: 32GB RAM + 128GB swap = 160GB total

nvme0n1p1 — EFI partition (DO NOT TOUCH — EVER)
    Ubuntu shimx64.efi lives here
    Both boot entries point here
    Wiping this = no boot
```

**Non-negotiable constraints:**
- OLLAMA_HOST must always be 0.0.0.0
- nvme0n1p1 is untouchable
- config.py is never shared or printed

---

## The Database — Core Intelligence, Not Supporting Infrastructure

The SQLite database (swarm_memory.db) is not a logging system. It is the persistent intelligence layer that makes the swarm more than a stateless question-answering machine. Without it, every email starts cold. With it, the swarm accumulates verified knowledge, individual agent experience, audit history, and queue state across every interaction.

### Memory pools — who writes, who reads, what it means

**Shared verified memory (memory table)**
Written by: Librarian only, via promote_to_verified
Read by: All agents via build_shared_context()
Content: One's verified verdicts, importance 9
Never archived — this is the permanent knowledge base
This is what the swarm knows with confidence. Every fact here has passed through One's synthesis, Duck's sanity check, and Sniffles' audit.

**memory_llama**
Written by: Two (self-indexed via Librarian tagging)
Read by: Two and One
Importance: 5
Two's personal research notebook. Grows with each web search.

**memory_mistral**
Written by: Three (self-indexed via Librarian tagging)
Read by: Three and One
Importance: 5
Three's analytical and debate history.

**memory_qwen**
Written by: Qwen (self-indexed via Librarian tagging)
Read by: Qwen and One
Importance: 5
Qwen's deep analysis history. Builds pattern recognition over time.

**memory_gemma** *(renamed to memory_one — migration pending)*
Written by: One (verdicts only, source='verdict')
Read by: One and Sniffles
Importance: 9, permanent, never archived
One's verdict history. Sniffles reads this to check for drift.

**duck_log**
Written by: Duck after every sanity check
Read by: Duck (reads own history — no repeat jokes), Ghost Circle
Every quack logged with timestamp, ticket reference, YES/NO result, and agent reactions. Duck's weekly morale report is generated from this log. This is how Duck improves over time — pattern recognition across its own history without touching the shared memory pool.

**sniffer_memory**
Written by: Sniffles after each audit
Read by: Sniffles (for pattern detection), Ghost Circle only
Not to be confused with sniffer_log (the audit event log). Sniffer_memory is Sniffles' pattern intelligence — "LLaMA overconfident 3x this week", "Qwen contradicted verified memory twice in 48 hours." This is what enables escalation levels: bark for individual incidents, pattern bark for trends, emergency for systemic failure. Individual barks go to agents and Ghost. Pattern reports go to Ghost Circle only.

**Ticket tables (queue, tickets, ticket_notes, duck_log)**
The operational layer. Queue holds waiting emails. Tickets track the full lifecycle (WAITING → IN_PROGRESS → PENDING_CLOSURE → CLOSED). Ticket_notes hold every agent's contribution to the deliberation. Duck_log holds every sanity check with timestamp and result.

### The Memory Design Principle

**Importance is the filter. Relevance is the gate. Time is the sort. Nothing else limits what an agent can see.**

This is not a filing system with quotas. Arbitrary count limits have been removed from every database query function. An agent does not see "the last 5 entries" — it sees everything above its importance threshold that matches the query, ordered by importance then time. The database does not decide what matters. Importance scores and query relevance do.

Importance scale in practice:
- 9 — Gemma verified verdict. Permanent. Never archived. All agents read via shared pool.
- 7 — Librarian indexed content. Significant but unverified.
- 5 — Agent personal working notes. Archived after 60 days.
- 3 — Minimum threshold for agent memory queries. Below this is noise.

Memory treated this way becomes a weapon not a filing cabinet. Each agent enters every ticket with the full weight of everything it has learned that is relevant to this question, above the noise floor, ordered by what mattered most. The swarm gets smarter every time it processes an email — not by accumulating entries, but by accumulating verified importance.

---

## The Ghost Circle — Full Visibility Layer

The Ghost Circle is a private layer accessible only to Ghost and Claude via API. It aggregates the Sniffles audit log, Duck's quack log, and the Claude advisory log into a single unfiltered view of swarm health.

### Claude's role in the Ghost Circle
Claude is called by Gemma when she is genuinely stuck — not as a first resort, but as a last one. When called, Claude sees the current ticket, all agent notes, relevant shared memory, Duck's full log, and Sniffles' full audit history. Claude responds with a recommendation that is stored in claude_log and memory_gemma. Gemma learns from each call — if the same type of problem arises again, Gemma checks memory_gemma before calling Claude. Over time the frequency of Claude calls decreases as Gemma internalises the patterns.

**claude_api.py — BUILT and LIVE.** The Ghost Circle advisor layer is wired in. Set ANTHROPIC_API_KEY in the environment to activate.

**Claude's position:** Mentor not driver. Silent until called. Sees everything in the Ghost Circle. Never speaks directly to email senders. Never appears in the public-facing pipeline.

---

## Full System Flow

```plaintext
EXTERNAL WORLD
    │
    │ email arrives at sevenpotato9@gmail.com
    ▼
listener.py — IMAP poll every 60 seconds
    │
    ▼ classify_sender()
    ├── SELF (Seven's own addresses) → skip, never reply to own emails
    ├── NOTIFICATION sender → file to Gmail label silently, no ticket
    ├── UNKNOWN sender → save to pending_emails, ask Ghost to TRUST/NOTIFY/IGNORE
    │                     on TRUST command: auto-process the pending email
    └── TRUSTED sender → continue below
    │
    ▼
LIBRARIAN INTAKE (RL-004)
    • Check RAM/CPU — if RAM <4GB, hold and reply "at capacity"
    • Strip noise: subject prefixes, signatures, reply chains
    • Generate 3-5 tags from body peek
    • Assign TICKET-{timestamp}
    • Store in queue table with system state snapshot
    • Auto-reply: "You are #N in queue, estimated wait: Xmin"
    │
    ▼
TICKET CREATED (RL-005)
    • ticket_number = TICKET-{conv_id}
    • status = 'open'
    • Linked to queue_id
    │
    ▼
GEMMA READ RECEIPT — Email 0 (RL-006)
    • Fired BEFORE any model processing
    • "I have read your question. The swarm is deliberating."
    • Gemma's voice — not a generic acknowledgment
    │
    ▼
STAGE 1 — consult_stage1()
    • Gemma reads question — FL-001 routing decision
    • If NEEDS_WEB=yes: LLaMA loads → searches DuckDuckGo → writes note → unloads
    • Email 1 sent: "[LLaMA]: answer + sources"
    │
    ▼
STAGE 2 — consult_stage2()
    • Three loads → reads ticket + Two's note → deepens or challenges → writes note → unloads
    • One loads → reads all notes → synthesises final verdict
    • Verdict → memory_gemma → promote_to_verified via Librarian
    • Librarian saves Vortex checkpoint on close
    • Email 2 sent: "[Three] + [One — Final verdict]"
    │
    ▼
DUCK SANITY CHECK — after every ticket
    • Duck loads (tiny, fast, 3-5 seconds)
    • "Does this answer make basic factual sense? YES or NO"
    • YES → ticket passes, quack logged, Librarian closes (RL-007)
    • NO  → flag_for_sniffles(), sniffles_result = 'DUCK_FLAGGED'
    │
    ▼
LIBRARIAN CLOSES TICKET (RL-007)
    • Indexes final Q&A to shared memory (importance 9)
    • Updates ticket status → 'closed'
    • Sets sniffles_checked = 0 (ready for audit)
    • Marks queue entry → 'completed'
    • Updates queue positions for waiting senders
    • Checks resources before opening next ticket
    │
    ▼
SNIFFLES TRIGGER
    • RL-008: Random 1-in-5 chance per email processed
    • Always runs if Duck flagged + queue quiet 1+ hour
    • Audits all memory tables for new unaudited entries
    • PASS / WARN / FLAG per entry
    • FLAG stops the queue — agents must correct, Gemma rules
    • Emails Ghost + Moderator if anything flagged
    • Writes to sniffer_log
    │
    ▼
next email picks up in 60 seconds
```

---

## Why These Specific Models — The Weighting Rationale

**gemma3:latest at 0.3** — Gemma needs to be the most reliable voice in the swarm. Gemma3 produces structured, consistent outputs which is exactly what FL-001 requires. Low temperature because orchestration errors cascade through the entire pipeline. A creative orchestrator is a dangerous orchestrator.

**llama3.2:latest at 0.6** — LLaMA is the researcher. It needs enough warmth to be conversational and enough looseness to synthesise web results into readable answers. 0.6 is the sweet spot between "too literal to summarise" and "too creative to be accurate." LLaMA3.2 specifically because it handles web content well and is fast to load/unload.

**qwen2.5:latest at 0.7** — Qwen needs to challenge. A cold analyst doesn't push back convincingly. 0.7 gives Qwen the confidence to say "LLaMA is wrong about this" and the reasoning depth to explain why. Qwen2.5's multilingual training is what makes it occasionally write in Chinese when the reasoning gets intense — its internal representation is richer than English-only models.

**qwen:1.5b (Librarian and Duck) at 0.1** — Both roles require precision over creativity. The Librarian generates tags, not prose. Duck answers YES or NO. Tiny model, coldest temperature, mechanical tasks. Using a large model here would be wasteful and potentially dangerous — a creative Librarian might decide to interpret content rather than just tag it.

**deepseek-r1:7b (Sniffles) at default** — DeepSeek R1's distinguishing feature is chain-of-thought reasoning that is visible and auditable. Sniffles must show its work — not just FLAG an entry but explain why in full reasoning chains. This is what makes Sniffles trustworthy. An auditor that doesn't show its reasoning cannot itself be audited.

---

## Agent Personalities — Persistent Through Prompt Engineering

Each agent's character is not emergent — it is enforced through system prompts in config.py that never change. The personality IS the constraint.

The Librarian never speaks because the prompt says so. Duck answers only YES or NO because the prompt enforces it. Sniffles cannot be silenced because the architecture won't allow it — it runs as a separate process triggered by conditions, not by agent consensus. Gemma speaks last and definitively because the prompt builds that authority into every response. LLaMA is chatty because 0.6 temperature combined with a research-focused prompt produces that character naturally. Qwen is spicy in debates because the prompt explicitly grants it permission to challenge and disagree.

The reason this matters: character consistency across thousands of interactions is what makes the swarm feel coherent rather than random. A swarm that behaves differently each session is not trustworthy. These agents behave the same way every time because the constraints are structural, not emergent.

---

## Database Schema — Complete

### All 40+ tables (swarm_memory.db — canonical DB)

| Table | Purpose |
| ----- | ------- |
| agents | Agent registry — 12 agents seeded |
| conversations | Conversation log |
| messages | All agent messages per conversation |
| memory | Shared verified pool — One's verdicts, importance 9, never archived |
| memory_llama | Two (LlaMA) research notebook |
| memory_mistral | Three (Mistral) analytical history |
| memory_qwen | Qwen deep analysis history |
| memory_gemma | One verdict history — Sniffles reads this (rename to memory_one pending) |
| memory_eight | Eight SAP specialist memory |
| memory_nine | Nine system architect memory |
| memory_ten | Ten (Github/GPT) memory |
| memory_grok | Eleven (Grok) memory |
| memory_sonic | Sonic slot (reserved, empty) |
| memory_scholar | Scholar slot (reserved, empty) |
| memory_seeker | Seeker slot (reserved, empty) |
| queue | Waiting emails — Librarian manages |
| tickets | Full ticket lifecycle |
| ticket_notes | Agent contributions per ticket |
| duck_log | Every sanity check with result and reason |
| sniffer_log | Every audit event with chain of thought |
| sniffer_memory | Sniffles' pattern intelligence across audits |
| trusted_senders | Full pipeline access |
| moderators | Ghost level — receives all reports |
| notification_senders | Silent filing, no response |
| pending_emails | Unknown senders awaiting Ghost approval |
| ghost_circle | Aggregated visibility — Ghost and Claude only |
| claude_log | Every Claude advisory call with token count |
| system_stats | RAM, CPU, swap, active model — monitor.py writes |
| ghost_briefs | Nine's synthesised intelligence reports |
| decisions | Decision log — written by Librarian (Vortex engine) |
| time_events | Time Wizard event log |
| time_journal | Time Wizard journal entries |
| time_checkpoints | Checkpoint snapshots |
| time_machine | Time machine state |
| daily_checkpoint | Daily state captures |
| scheduled_tasks | Scheduler task registry |
| sandpit_log | File agent write/read audit log |
| activity_log | General swarm activity feed |

---

## Files — Current State (Post-Reorganization 2026-03-28)

All Python files are organized into directories. No flat-file structure at root.

| Location | File | Purpose | Status |
| -------- | ---- | ------- | ------ |
| core/pipeline/ | listener.py | Email loop — IMAP poll + Gmail push, classify, route | LIVE |
| core/pipeline/ | orchestrator.py | Agent pipeline — Gemma routes, agents run, synthesises | LIVE |
| core/pipeline/ | queue_manager.py | Librarian intake, queue management | LIVE |
| core/pipeline/ | ticket.py | Ticket lifecycle (open → closed) | LIVE |
| core/pipeline/ | debate.py | Three-round debate system — Gemma as judge | LIVE |
| agents/ghost/ | duck.py | Sanity checker — YES/NO after every ticket | LIVE |
| agents/ghost/ | sniffer.py | Memory auditor — PASS/WARN/FLAG, emails moderator | LIVE |
| agents/specialists/ | eight.py | SAP specialist — 3-voice reasoning | LIVE |
| agents/specialists/ | eight_memory.py | Memory persistence for Eight | LIVE |
| agents/specialists/ | agent_proposals.py | Agent play-time proposal framework | LIVE |
| agents/specialists/ | agent_email_ghost.py | Email approval/routing logic | LIVE |
| utils/ | database.py | Complete database layer — 40+ tables | LIVE |
| utils/ | config.py | All secrets + all system prompts — NEVER SHARE | LIVE |
| utils/ | claude_api.py | Ghost Circle — Gemma calls Claude when stuck | LIVE |
| utils/ | brief_engine.py | Nine's Ghost Brief generator | LIVE |
| utils/ | sandpits.py | Sandpit file operations | LIVE |
| utils/ | simulate.py | Simulation / testing harness | LIVE |
| lib/email/ | email_handler.py | Gmail IMAP/SMTP | LIVE |
| lib/email/ | email_cleaner.py | Strip signatures, reply chains | LIVE |
| lib/email/ | gmail_auth.py | OAuth2 Gmail authentication | LIVE |
| lib/email/ | gmail_push.py | Gmail push notification receiver | LIVE |
| lib/system/ | monitor.py | System performance daemon | LIVE |
| lib/system/ | housekeeping.py | Daily cleanup and memory archiving | LIVE |
| lib/system/ | contradiction_check.py | Compares new entries vs verified memory | LIVE |
| lib/system/ | system_clock.py | Unified timestamp functions | LIVE |
| lib/system/ | time_machine.py | Time machine state management | LIVE |
| lib/system/ | file_versioning.py | File change tracking | LIVE |
| lib/system/ | discord_notify.py | Discord notifications | LIVE |
| lib/system/ | logging_bridge.py | Ghost Circle logging | LIVE |
| lib/search/ | internet.py | DuckDuckGo web search | LIVE |
| lib/search/ | internet_serper.py | Serper.dev search | LIVE |
| lib/search/ | internet_tavily.py | Tavily AI search | LIVE |
| fridays/ | scheduler.py | Scheduled task runner (daily digest, brief) | LIVE |
| fridays/ | discord_bot.py | Discord bot service | LIVE |
| fridays/ | telegram_bot.py | Telegram bot service | LIVE |
| fridays/ | skills.py | Skills dispatcher framework | LIVE |
| fridays/ | shell_agent.py | Whitelisted shell command execution | LIVE |
| fridays/ | file_agent.py | Sandpit file read/write | LIVE |
| fridays/ | browser_agent.py | Headless browser (Playwright) | LIVE |
| frontend/ | terminal.py | Fridays web terminal (port 5050) | LIVE |
| frontend/ | theme_engine.py | Time-of-day CSS theme injection | LIVE |

---

## Security Layer

Ollama (port 11434) and Open WebUI (port 3000) are behind Tailscale VPN. Only accessible from devices on the Tailscale network. Public internet cannot reach either service.

Claude API key lives in /etc/environment — not in config.py at runtime. Rotate quarterly.

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
11. Claude API is built last — local pipeline must be stable first
12. Ghost Circle dashboard is read-only when built
13. Ollama port 11434 — Tailscale only
14. Open WebUI port 3000 — Tailscale only
15. Claude API key in /etc/environment — never in config.py
16. Tailscale/VPN keys never stored in the swarm repository
17. Memory limits are set by importance threshold, never by count

---

---

## Frontend Architecture — Current State & Evolution Path

*Decided: 2026-04-04. Owner: Ghost + Nine.*

### Current State (Monolith)

The Fridays UI is a single-file monolith:
- `frontend/terminal.py` — ~16,000+ lines of Python. All Flask routes for all tiles in one file.
- `frontend/templates/terminal_base.html` — ~16,500 lines. All tile HTML + JavaScript in one file.

**Problem:** Any edit to one tile risks breaking every other tile. A bad edit to the Chat tile crashes the whole server. Editing safely at this scale requires treating the file like live surgery.

### Target State (Tile Module Architecture)

Each tile becomes a self-contained unit. The base layer becomes a thin shell.

```plaintext
frontend/
  terminal.py                    ← base only: startup, auth, ALM gate, blueprint registration
  tiles/
    chat/
      routes.py                  ← all /api/chat/* Flask routes (Blueprint)
      chat.js                    ← Chat tile JavaScript (ES module)
      chat.html                  ← Chat tile HTML fragment
    terminal_tile/
      routes.py
      terminal.js
      terminal.html
    files/
      routes.py
      files.js
      files.html
    alm/
      routes.py
      alm.js
      alm.html
    monitor/
      routes.py
      monitor.js
      monitor.html
  static/
    utils/
      ui.js                      ← shared: showToast, _escHtml, winManager
      api.js                     ← shared fetch helpers
  templates/
    base.html                    ← shell: loads shared JS/CSS, fetches + injects tile fragments
```

**How tile injection works (no build tooling needed):**
The base HTML loads, then fetches each tile's HTML fragment from its own route and injects it into the DOM. Tiles are self-contained HTML+JS served by their own blueprint. No Jinja2 server-side rendering required.

**How Flask blueprints work:**
`terminal.py` scans `tiles/*/routes.py` and auto-registers each as a Flask Blueprint. Adding a new tile = create a folder + `routes.py` + register. Removing a tile = delete the folder.

### Desktop Application Path

Long-term target: standalone desktop app via **Electron** or **Tauri**.

- Flask runs as a bundled local subprocess on `localhost:5050`
- Electron/Tauri wraps the web frontend as the app shell
- Nothing in the Flask backend changes — it remains the API layer
- The ES module frontend transfers directly into the desktop build

**Why this path:**
- The stack is already web-native (Python/Flask + HTML/JS)
- No rewrite of backend logic required
- Electron has the largest ecosystem; Tauri is lighter (Rust, uses OS webview)
- Either option works — the frontend modularisation done now is the prerequisite

**What transfers directly:**
- Flask Blueprints → same, running as local subprocess
- ES module JS tiles → same, loaded by Electron/Tauri webview
- SQLite database → bundled with the app
- Ollama → local, already running separately

**What needs new work at desktop time:**
- App packaging (electron-builder / Tauri CLI)
- Auto-update mechanism
- System tray integration
- Native file dialogs (optional — current file tile works fine without them)

### Migration Sequencing

Tiles are reviewed and extracted one at a time. Each tile is only moved when it has been:
1. Fully reviewed (issues documented)
2. Bugs fixed
3. Code cleaned to a standard that makes extraction safe

**Status:**

| Tile        | Review                    | Bugs Fixed              | Extracted     |
| ----------- | ------------------------- | ----------------------- | ------------- |
| Chat        | ✅ Done (2026-04-04)      | ✅ 5 fixes applied      | ⬜ Pending    |
| Terminal    | 🔄 In progress            | ⬜ Pending              | ⬜ Pending    |
| Files       | ⬜ Not started            | —                       | —             |
| ALM/Studio  | ⬜ Not started            | —                       | —             |
| Monitor     | ⬜ Not started            | —                       | —             |
| Vortex      | ⬜ Not started            | —                       | —             |

---

*The Ghost speaks. The swarm thinks. The Librarian remembers.*
*The Duck checks. Sniffles watches. Claude advises when asked.*
*You can only do what you can do when you can do it.*
