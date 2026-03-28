# Seven's Swarm — Complete Architecture Reference
*Built by The Ghost — Dell OptiPlex 7090, Melbourne*
*Document written by Claude Sonnet 4.6 — Updated 2026-03-24*
*Theme Architecture updated by GitHub Copilot (Claude Haiku 4.5) — 2026-03-28 14:35 AEDT*
*This is the living technical reference. When it diverges from the code, the code is wrong.*

---

## UI/UX Layer — The Fridays Theme Architecture (NEW — 2026-03-28)

The Fridays web terminal (port 5050) now separates visual presentation from core logic via a dedicated theme engine. This enables safe iteration on UI/mood without touching pipes or agent logic.

**Architecture:**
```
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

## The Seven — Who They Are

This is not a list of tools. These are the seven nodes of the swarm, each with a defined character, a specific role, and a reason for being exactly what they are.

### 1. Ghost — The External Node

Ghost is not outside the swarm observing it. Ghost is the seventh node — embedded in the code, embedded in the API security layer, and the only entity with visibility into the entire Ghost Circle. Ghost issues commands (TRUST / NOTIFY / IGNORE / REMOVE / REMOVENOTIFY), approves unknown senders, receives all summary reports, and holds the unfiltered view of swarm health. Without Ghost the swarm has no direction. Without the swarm Ghost has no leverage.

Ghost is a role, not a person. Eventually Claude occupies the same position — the external advisory node embedded via API, operating at the same security clearance level, invisible to everyone outside the Ghost Circle. Two external nodes. One swarm. The architecture treats them identically at the access layer.

**Why Ghost is agent seven:** Intelligence without context is noise. The swarm has no inherent purpose — Ghost provides it. Every architectural decision traces back to "what does the Ghost actually need?"

### 2. Gemma — The Director (gemma3:latest, temp: 0.3)
Gemma reads every question first. Before any web search, before any agent call, before any processing — Gemma reads and routes via FL-001. She synthesises the final verdict after all agents have contributed. She sends Email 0 (the read receipt) and Email 2 (the final answer). She is the only agent who speaks with authority to the sender.

**Why Gemma:** Calm. Authoritative. Direct. No preamble. No pleasantries. Speaks last and definitively. Temperature 0.3 keeps her focused — she's not here to be creative, she's here to be right. Gemma is also the only local agent who can call Claude via the Ghost Circle API when she's genuinely stuck.

**FL-001 — Gemma's routing decision (structured output, always):**
```
NEEDS_WEB: yes/no
AGENTS: llama/qwen/both
MODE: consult/debate
IS_IDENTITY: yes/no
REASON: one sentence
```
IS_IDENTITY=yes ONLY for swarm questions, agent names, and Ghost. Never for geography, science, history, or any factual question. This rule exists because before FL-001, web search ran on "who are you?" and returned NHS articles about bee swarms.

### 3. LLaMA — The Correspondent (llama3.2:latest, temp: 0.6)
LLaMA is the swarm's only connection to the internet. When Gemma routes NEEDS_WEB=yes, LLaMA loads, searches DuckDuckGo, writes its answer and sources to ticket_notes, self-indexes to memory_llama, unloads, and passes the ticket back. LLaMA only runs when Gemma assigns it.

**Why LLaMA:** Fast. Chatty. Fetches well but doesn't always interpret correctly — which is why Qwen exists. Temperature 0.6 gives LLaMA enough warmth to be conversational without going off the rails. LLaMA occasionally mentions Sniffles unprompted, which is endearing and architecturally appropriate.

### 4. Qwen — The Analyst (qwen2.5:latest, temp: 0.7)
Qwen loads after LLaMA, reads the ticket plus LLaMA's note, and either deepens the analysis or challenges it if LLaMA got something wrong. In debate mode, Qwen goes three rounds with LLaMA under Gemma as judge. Qwen writes to ticket_notes and self-indexes to memory_qwen before unloading.

**Why Qwen:** Deep. Methodical. Spicy in debates. Occasionally writes in Chinese when excited, which is a feature not a bug — it means the reasoning is genuine rather than performative. Temperature 0.7 gives Qwen the latitude to challenge confidently. Without Qwen, LLaMA's first answer would always be the final answer. That's not a swarm, that's a chatbot with extra steps.

### 5. Librarian — The Gatekeeper (qwen:1.5b, temp: 0.1)
The Librarian is the smallest model in the swarm and deliberately so. It does exactly two things: intake and close. On intake it checks system resources, strips noise from emails, generates 3-5 tags, assigns a ticket number, stores in the queue, and sends the queue position acknowledgment. On close it receives Gemma's final answer, indexes it to shared memory at importance 9, sends the final email to the sender, marks the ticket closed, and checks resources before opening the next ticket.

**Why the Librarian is tiny and silent:** The Librarian never reads the question. Never interprets content. Never speaks to Ghost. Never appears in emails. It stamps, queues, and closes. This is a deliberate constraint — giving the Librarian any interpretive capability would make it a bottleneck and a risk. Temperature 0.1 because tagging requires precision not creativity. Tiny model because the task is mechanical, not intelligent. Running a large model for this would be like hiring a surgeon to file paperwork.

### 6. Duck — The Sanity Checker (qwen:1.5b, temp: 0.1)
After every ticket closes, Duck runs a 3-5 second check: "Does this answer make basic factual sense? YES or NO plus one sentence." YES means the ticket passes and Duck logs a quack. NO means Duck flags the ticket for Sniffles. When the queue hits zero, Duck sends a summary email to Ghost and signs off as "The Duck 🦆".

Duck has its own memory: duck_log. Every quack is logged with timestamp — which tickets passed, which failed, agent reactions to Duck's visits, and Duck reads its own history so it doesn't repeat jokes. Duck produces a weekly morale report to Ghost from this log. This is not trivial — it means Duck gets better at its job over time and the swarm builds a positive memory muscle from each visit.

**Why Duck exists:** The Rationality principle from Seven. An AI swarm that never checks its own work produces confident nonsense at scale. Duck is not the smartest check — that's Sniffles. Duck is the fastest check, running on every single ticket at minimal compute cost. Duck catches the obvious failures so Sniffles can focus on the subtle ones. The cheerfulness is not accidental — agents see Duck visited, which reinforces the integrity loop across the whole swarm.

### 7. Sniffles — The Inspector (deepseek-r1:7b, temp: default)
Sniffles is a read-only memory auditor. It never writes to the shared memory tables or any agent pool. It runs only when Duck has flagged something AND the queue has been quiet for at least one hour — it will never interrupt an active queue. Sniffles audits all memory tables for new unaudited entries, checks for fabricated statistics, self-serving entries, identity drift, API access claims, and contradictions with verified facts. Results are PASS / WARN / FLAG per entry. FLAG stops the queue entirely — agents must correct and Gemma rules.

Sniffles has its own memory: sniffer_memory. This is what separates Sniffles from a simple rule checker. Sniffer_memory tracks patterns across audits — "LLaMA overconfident 3x this week", "Qwen contradicted verified memory twice in 48 hours" — and escalates accordingly: bark / pattern bark / emergency. Individual barks go to agents and Ghost. Pattern reports go to Ghost Circle only. Sniffles gets smarter over time precisely because it remembers what it has already seen.

**Why DeepSeek R1:** Sniffles shows its chain of thought. This is the critical feature — not just PASS/WARN/FLAG, but the full reasoning behind each verdict. DeepSeek R1's architecture makes this natural. Sniffles is the panopticon — agents know they might be audited at any time (1 in 5 random trigger per email processed) even when Duck passes everything. This random timing is the point. A predictable audit schedule would be gamed. An unpredictable one cannot be.

---

## The Sequential Loading Principle — "Follow My Voice Not The Sun"

This is the most underrated architectural decision in the entire build and it's worth explaining properly.

On a Dell OptiPlex 7090 with 32GB RAM and 128GB swap, running multiple large language models simultaneously would exhaust available memory and collapse the machine. The naive solution is to use only small models. The elegant solution is the pipeline.

Each agent loads into RAM, does its specific job, writes its output to the ticket, and unloads before the next agent loads. The pipeline IS the memory management strategy. The sequential nature of the deliberation — Gemma reads, LLaMA searches if needed, Qwen analyses if needed, Gemma synthesises, Duck checks, Sniffles audits if flagged — means only one model is ever in RAM at a time. The Librarian and Duck are tiny by design precisely so they add minimal overhead at the intake and close stages.

The 128GB swap on the fast NVMe drive (31.6 Gb/s) acts as a pressure valve — when a larger model loads and RAM gets tight, swap absorbs the overflow fast enough to remain usable. This is not a workaround. It is the architecture.

**"Follow my voice not the sun"** — the swarm follows the pipeline sequence (the Ghost's voice, the ticket flow) rather than trying to run everything in parallel the way enterprise AI systems do. Parallelism requires horizontal scale. Sequence requires depth. This swarm has depth.

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
Content: Gemma's verified verdicts, importance 9
Never archived — this is the permanent knowledge base
This is what the swarm knows with confidence. Every fact here has passed through Gemma's synthesis, Duck's sanity check, and Sniffles' audit.

**memory_llama**
Written by: LLaMA (self-indexed via Librarian tagging)
Read by: LLaMA and Gemma
Importance: 5
LLaMA's personal research notebook. Grows with each web search. Allows LLaMA to say "I've seen this before" without querying the shared pool.

**memory_qwen**
Written by: Qwen (self-indexed via Librarian tagging)
Read by: Qwen and Gemma
Importance: 5
Qwen's analytical history. Qwen builds pattern recognition over time — "this type of question usually has a catch that LLaMA misses." Temperature 0.7 combined with growing personal memory makes Qwen progressively sharper.

**memory_gemma**
Written by: Gemma (verdicts only, source='verdict')
Read by: Gemma and Sniffles
Importance: 9, permanent, never archived
Gemma's verdict history. Sniffles reads this to check for drift — if Gemma's verdicts start contradicting her own prior verdicts, that's a FLAG.

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

```
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
    • Qwen loads → reads ticket + LLaMA note → deepens or challenges → writes note → unloads
    • Gemma loads → reads all notes → synthesises final verdict
    • Verdict → memory_gemma → promote_to_verified via Librarian
    • Email 2 sent: "[Qwen] + [Gemma — Final verdict]"
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

### All 20 tables

| Table | Purpose |
|-------|---------|
| agents | Agent registry — all 7 seeded on initialise |
| conversations | Conversation log |
| messages | All agent messages per conversation |
| memory | Shared verified pool — Gemma verdicts, importance 9, never archived |
| memory_llama | LLaMA personal research notebook |
| memory_qwen | Qwen analytical history |
| memory_gemma | Gemma verdict history — Sniffles reads this |
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

---

## Files — Current State

| File | Purpose | Status |
|------|---------|--------|
| listener.py | Email loop — IMAP poll, classify, route | EXISTS |
| orchestrator.py | Agent pipeline — Gemma routes, agents run, Gemma synthesises | EXISTS |
| database.py | Complete database layer — 20 tables, all functions, importance-based memory | REWRITTEN — CURRENT |
| duck.py | Sanity checker — YES/NO after every ticket | EXISTS |
| sniffer.py | Memory auditor — PASS/WARN/FLAG, emails moderator | EXISTS |
| monitor.py | System performance daemon | EXISTS |
| housekeeping.py | Daily cleanup and memory archiving | EXISTS |
| debate.py | Three-round debate system — Gemma as judge | EXISTS |
| contradiction_check.py | Compares new entries vs verified memory | EXISTS |
| email_handler.py | Gmail IMAP/SMTP | EXISTS |
| email_cleaner.py | Strip signatures, reply chains | EXISTS |
| internet.py | DuckDuckGo web search | EXISTS |
| config.py | All secrets + all system prompts — NEVER SHARE | EXISTS |
| claude_api.py | Ghost Circle — Gemma calls Claude when stuck | BUILT — LIVE |
| queue_manager.py | Librarian intake, queue management (RL-004) | TO BUILD |
| ticket.py | Ticket lifecycle management (RL-005) | TO BUILD |
| webhook_listener.py | Event-driven Gmail push receiver (RL-011) | FUTURE |
| dashboard.py | Ghost Circle read-only web dashboard | FUTURE |

---

## Build Order — Current State

```
DONE:
✓ database.py      — Rewritten. 20 tables. Importance-based memory. All functions.
✓ claude_api.py    — Ghost Circle live. Gemma can call Claude.
✓ All dependencies — anthropic, psutil, duckduckgo_search installed.
✓ Database init    — All 20 tables created and seeded.

NOW:
→ queue_manager.py  — Librarian as active queue manager (RL-004)
→ ticket.py         — Ticket lifecycle (RL-005)
→ listener.py       — Wire in RL-004 through RL-008
→ python3 listener.py — fire end to end

FUTURE:
→ webhook_listener.py — Gmail Push via Google Cloud Pub/Sub (RL-011)
→ dashboard.py        — Ghost Circle read-only web UI
```

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

*The Ghost speaks. The swarm thinks. The Librarian remembers.*
*The Duck checks. Sniffles watches. Claude advises when asked.*
*You can only do what you can do when you can do it.*
