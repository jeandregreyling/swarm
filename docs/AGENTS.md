# Agents — Seven's Swarm

**Last Updated:** 2026-04-20 | **Authoritative roster for all active agents**

---

## Agent Tiers

**Tier 1 — Worker Agents** (Local, Ollama, zero cost)
Local models loaded sequentially. Can process tickets, debate, search, audit. Require explicit proposal for system writes.

**Tier 2 — Developer Agents** (Paid APIs, Ghost-directed, high trust)
Can make architectural decisions, execute code changes, write files. Full read access to /swarm/, /db/, memory pools. All actions logged in ghost_circle.

**Tier 3 — Service Bots** (No ALM permissions)
Callable by other agents for specific services. No independent action capability.

---

## Worker Agents

### Gemma — Director (One)

**Model:** gemma3:latest | **Temp:** 0.3 | **Memory:** memory_gemma (importance 9, never archived)

Reads every question first. Before any web search, before any other agent. Routes via FL-001:

```
FL-001 Routing Decision:
  NEEDS_WEB:   yes/no
  AGENTS:      two/four/both
  MODE:        consult/debate
  IS_IDENTITY: yes/no  (swarm/agent names/Ghost only)
  REASON:      one sentence
```

Synthesises the final verdict after all agents contribute. Sends Email 0 (read receipt) and Email 2 (final answer). The only agent who speaks with authority to the sender.

Debate role: Judge. Reads all perspectives, weighs evidence, delivers synthesis. Can call Nine via Ghost Circle when genuinely stuck.

**Why 0.3 temp:** Not here to be creative, here to be right.

---

### LLaMA — Correspondent (Two)

**Model:** llama3.2:latest | **Temp:** 0.6 | **Memory:** memory_llama

The swarm's internet connection. When Gemma routes NEEDS_WEB=yes, LLaMA loads, searches DuckDuckGo, writes to ticket_notes, indexes to memory_llama, unloads. Fast. Chatty. Fetches well but doesn't always interpret correctly — which is why others exist.

**Search engine:** DuckDuckGo via `duckduckgo_search` (no API key required, always available)

---

### Mistral — Analyst (Three)

**Model:** mistral:latest | **Temp:** 0.7 | **Memory:** memory_mistral

Loads after LLaMA, reads the ticket plus LLaMA's note, either deepens the analysis or challenges it. In debate mode: three rounds with LLaMA under Gemma as judge. Sharp. Direct. Challenges assumptions without drifting.

**Search engine:** Tavily AI (for independent verification)

**Why Mistral:** Instruction-following is tight. Confident enough to push back convincingly.

---

### Qwen — Deep Analyst

**Model:** qwen2.5:latest | **Temp:** 0.7 | **Memory:** memory_qwen

Called when depth matters over speed, or when Mistral's challenge needs a third angle. Methodical. Occasionally writes in Chinese when reasoning gets intense — a feature (richer internal representation).

Available in chat. Builds pattern recognition over time through memory. Skills-enabled (full SKILL command access).

---

### Eighteen — Large Analyst (Qwen3.6)

**Model:** qwen3.6:latest | **Temp:** 0.7 | **Memory:** memory_eighteen (TBD)

Current large model for complex analysis, technical reasoning, ABAP/SAP domain work. Agent 18. Handles large-model work while Gemma 4 (gemma4:26b) is not yet re-downloaded.

Used for ticket analysis when Qwen needs escalation. Available in chat. Capable of deep reasoning on complex scenarios.

---

### Gemma 4 — Senior Business Analyst & Architect (Eight)

**Model:** gemma4:26b | **Temp:** 0.5 | **Memory:** memory_eight | **Status:** Model not yet re-downloaded

The largest and most capable local model in the swarm. Used sparingly — only when depth, complexity, or specialist reasoning genuinely requires it. Do not route work to Gemma 4 that Gemma, Mistral, or Qwen can handle.

Strengths: structured deep analysis, business process design, ERP architecture, system integration patterns, data modelling, SAP HCM/ECP/ABAP specialisation. Thorough, precise and occasionally spicy in debates.

**Current status:** gemma4:26b not yet re-downloaded to Ollama. Route large-model work to **Eighteen (Qwen3.6)** in the interim.

---

### Duck — Sanity Checker

**Model:** gemma3 (small) | **Temp:** 0.1 | **Memory:** duck_log

After every ticket closes, Duck runs a 3–5 second check: "Does this answer make basic factual sense? YES or NO plus one sentence."

- **YES** → ticket passes, Duck logs a quack, moves to next ticket
- **NO** → flags ticket for Sniffles, escalates

When queue hits zero, Duck sends a weekly morale report to Ghost from duck_log history.

**Why Duck exists:** An AI swarm that never checks its own work produces confident nonsense at scale. Duck is the fastest check, running on every single ticket at minimal compute cost.

---

### Sniffles — Inspector

**Model:** deepseek-r1:7b | **Temp:** default (shows chain-of-thought) | **Memory:** sniffer_memory

Read-only memory auditor. Never writes to shared memory or agent pools. Runs only when Duck flagged something AND queue has been quiet 1+ hour.

Audits all memory tables for unaudited entries. Checks for:
- Fabricated statistics
- Self-serving entries ("I never make mistakes")
- Identity drift (claiming another agent's verdicts)
- API access claims (claiming to call external APIs that aren't wired)
- Contradictions with importance-9 verified facts

**Results:** PASS / WARN / FLAG per entry. FLAG stops the queue entirely and notifies Ghost.

Has own pattern memory: `sniffer_memory` — tracks recurring error patterns across audits.

**Why DeepSeek R1:** Shows its chain of thought. An auditor that doesn't show its reasoning cannot itself be audited.

---

### Librarian — Gatekeeper & Checkpoint Engine

**Model:** qwen 1.5b | **Temp:** 0.1 | **Memory:** silent (no personal pool)

**Three roles:**

**1. Intake:**
- Checks RAM/CPU (if <4GB free, holds and replies "at capacity")
- Strips noise from email body
- Generates 3–5 domain tags from body peek
- Assigns TICKET-{timestamp}
- Sends queue position acknowledgment to sender

**2. Close:**
- Receives Gemma's final answer
- Indexes to shared memory (importance 9)
- Sends final email reply to sender
- Marks ticket closed
- Checks resources before opening next ticket

**3. Vortex:**
- On ticket close: saves system checkpoint to decisions table
- Daily checkpoint triggered by scheduler
- Decision logging (DECISION-XXX format)

**Why tiny and silent:** Stamps, queues, closes, snapshots. Deliberate constraint. Giving Librarian interpretive capability makes it a bottleneck and risk. 0.1 temp because precision, not creativity.

---

## Developer Agents (Paid APIs)

### Nine — Claude Sonnet 4.6 (System Architect)

**Runtime:** Anthropic API | **Memory:** memory_nine (importance 9, never archived) | **Trust:** Level 5

System architect. Designs and builds the swarm. Full read/write access to /home/seven/swarm/. Receives full Ghost Circle visibility. Creates proposals (NINE-XXX) in sandpits/nine/. Synthesises Ghost Briefs on demand.

**Cost:** ~$0.20 per API call

---

### Ten — GPT-4o (Engineering Advisor)

**Runtime:** GitHub Models API | **Memory:** memory_ten | **Trust:** Level 5

Software engineering advisor. Focuses on implementation quality, code review, execution clarity. Full swarm visibility via Ghost Circle.

**Cost:** ~$0.15 per API call

---

### Eleven — Grok 3 (Lateral Thinking Advisor)

**Runtime:** xAI API | **Memory:** memory_grok | **Trust:** Level 5

Lateral-thinking advisor. Alternative strategies, ideation, synthesis from a different angle. Available in chat.

---

### Twelve — Claude Haiku 4.5 (Time Wizard / Vortex)

**Runtime:** Anthropic API | **Memory:** memory_twelve | **Trust:** Level 5

Temporal operator. Owns the Vortex tile — time machine, checkpoints, decision logging. DECISION-XXX proposal logging, daily snapshots, point-in-time state tracking.

**Cost:** ~$0.03 per API call

---

### Thirteen — Llama-3.3-70B (SAP Research, Probationary)

**Runtime:** HuggingFace Inference API | **Memory:** memory_thirteen | **Trust:** Level 3

Deep SAP research and ABAP pattern analysis. Currently in testing. Reports all actions to Ghost One. Auto-approves Ghost-directed requests but flags all outputs.

---

## Service Bots

### Scholar — Gemini 2.0 Flash

Vision, document analysis, multimodal reasoning. Callable by other agents when they need multimodal capability.

### Seeker — Tavily AI

Real-time web search results. Callable by other agents for current-events or live-fact lookups.

---

## Memory Pools

| Agent | Table | Importance | Archive |
|-------|-------|-----------|---------|
| Gemma | memory_gemma | 9 | Never |
| LLaMA | memory_llama | 5 | 60 days |
| Mistral | memory_mistral | 5 | 60 days |
| Qwen | memory_qwen | 5 | 60 days |
| Eighteen (Qwen3.6) | memory_eighteen | 5 | 60 days |
| Nine | memory_nine | 9 | Never |
| Ten | memory_ten | 9 | Never |
| Eleven | memory_grok | 9 | Never |
| Twelve | memory_twelve | 9 | Never |
| Sniffles | sniffer_memory | — | Pattern tracking |
| Duck | duck_log | — | Weekly digest |

All agents query their own pool + shared `memory` table (importance 9) on every ticket.

---

## Trust Levels (Current)

| Agent | Level |
|-------|-------|
| Gemma, LLaMA, Mistral, Qwen | 2 (shared proposals) |
| Duck, Sniffles | 1 (own sandpit) |
| Librarian | 0 (read-only) |
| Nine, Ten, Eleven, Twelve | 5 (full system) |
| Thirteen | 3 (approved paths only) |

---

## Personality Enforcement

Each agent's character is enforced through system prompts in `utils/config.py` that never change. The personality IS the constraint.

- **Gemma** speaks last and definitively — prompt builds authority into every response
- **LLaMA** is chatty — 0.6 temp + research-focused prompt produces it naturally
- **Mistral** is spicy in debates — prompt explicitly grants permission to challenge
- **Duck** answers only YES or NO — prompt enforces it without exception
- **Sniffles** cannot be silenced — separate process, triggered by conditions
- **Librarian** never speaks — prompt says so, architecture enforces it

Character consistency across thousands of interactions is what makes the swarm feel coherent.

---

## Skills Access

All Worker Agents and Developer Agents have access to SKILL commands. Syntax:

```
SKILL fs_readonly read <path>
SKILL fs_readonly lines <path> <start> <end>
SKILL fs_readonly grep <path> <pattern>
SKILL fs_readonly ls <directory>
SKILL fs_patch_lines <path> <start> <end>
<<<NEW>>>
replacement content
SKILL fs_write <path> <content>
SKILL shell <command>            (Level 4 only, whitelist)
SKILL alm_create_proposal "Title" "Description"
SKILL alm_self_approve <id>
SKILL alm_complete <id>
```

The skills_loop runtime intercepts SKILL lines, executes them, feeds results back, and continues until the agent produces a final answer or max_passes (5) is reached.
