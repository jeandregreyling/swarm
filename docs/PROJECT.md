# Seven's Swarm — Project Overview

**Last Updated:** 2026-04-20 | **Status:** Production, Phase 8+ | **Branch:** `proposal/GHOST_CODER-0890`

---

## Vision

A fully local, autonomous, multi-agent AI swarm that operates without cloud dependencies. Every action is debated, approved, executed, verified, and audited. The system runs on a single Dell OptiPlex with orchestrated sequential model loading that prevents resource exhaustion.

**The difference that matters:** A single model deletes the wrong file. A swarm that votes before acting does not. Every response is debated, every memory is audited, every file change is versioned.

**The three layers:**

```
SEVEN     — Local AI agents and decision pipeline
            Gemma (director), LLaMA (researcher), Qwen/Mistral (analysts)
            Librarian (gatekeeper), Duck (auditor), Sniffles (inspector)

EIGHTEEN  — Large analyst (Qwen3.6)
            Deep reasoning, complex analysis, large-model work while gemma4 not yet downloaded

FRIDAYS   — Action layer
            Discord/Telegram bots, file/shell/browser agents
            Skills framework, Tasker scheduler, sandpit enforcement
```

---

## Hardware & Infrastructure

```
Dell OptiPlex 7090
├─ CPU:   Intel Core i5-10500 (6-core, 12-thread, 3.1GHz) — CPU-only, no GPU
├─ RAM:   33GB
├─ OS:    Linux Mint 22.3 (dual-boot with Windows 10 22H2)
├─ Host:  seven-potato
└─ User:  seven

Storage:
├─ nvme1n1p1  469GB  ext4  — OS, apps, swarm code (/home/seven/swarm/)
├─ nvme0n1p2  120GB  NTFS  — Windows system partition
├─ nvme0n1p5   43.7GB ext4  — /mnt/swarm_drive (Linux data)
├─ nvme0n1p6   64GB  NTFS  — /mnt/ollama-models (shared model storage)
└─ nvme0n1p1  EFI — DO NOT TOUCH. Both boot entries point here.

Swap:
└─ /swap/swapfile  48GB  (active, NVMe at ~15.8 Gb/s)

Ollama Models:
└─ /mnt/ollama-models/.ollama/models
   OLLAMA_MODELS set in /etc/systemd/system/ollama.service.d/override.conf
   OLLAMA_HOST=0.0.0.0  (Tailscale-accessible)
```

**Memory strategy:** The 48GB swapfile is the architecture, not a workaround. Sequential model loading means peak usage stays within RAM+swap. NVMe swap at 15.8 Gb/s means thrashing is not the bottleneck — model compute is.

**Critical constraint:** `nvme0n1p1` (EFI) is untouchable. Wiping it = no boot on either OS.

---

## Current Agent Roster

### Worker Agents (Local, Ollama, zero cost)

| Agent | Model | Role |
|-------|-------|------|
| Gemma (One) | gemma3:latest | Director — routes via FL-001, synthesises verdict |
| LLaMA (Two) | llama3.2:latest | Correspondent — web search, fast answers |
| Mistral (Three) | mistral:latest | Analyst — challenges, debates |
| Qwen | qwen2.5:latest | Deep analyst — methodical reasoning |
| Eighteen (Qwen3.6) | qwen3.6:latest | Large analyst — complex reasoning, replaces Eight temporarily |
| Duck | gemma3 (small) | Sanity checker — YES/NO every ticket |
| Sniffles | deepseek-r1:7b | Inspector — audits memory with chain-of-thought |
| Librarian | qwen 1.5b | Gatekeeper — intake, tag, close, checkpoint |

### Developer Agents (Paid APIs, Ghost-directed)

| Agent | Model | Role |
|-------|-------|------|
| Nine | Claude Sonnet 4.6 | System architect, code review |
| Ten | GPT-4o | Engineering advisor |
| Eleven | Grok 3 | Lateral thinking, ideation |
| Twelve | Claude Haiku 4.5 | Time Wizard, Vortex, decision logging |
| Thirteen | Llama-3.3-70B | SAP/ABAP research (probationary) |

### Service Bots (No ALM permissions)

| Agent | Service | Role |
|-------|---------|------|
| Scholar | Gemini 2.0 Flash | Vision, multimodal reasoning |
| Seeker | Tavily AI | Real-time web search |

### Ghost (Human Operator)

Ghost is **Jeandre** (Ghost One). Not an AI. Not numbered. Full system authority. Issues commands, approves proposals, receives all reports.

> Note: "Gemma 4" (gemma4:26b) model not yet re-downloaded — agent Eighteen (Qwen3.6) handles large-model work in the interim.

---

## Memory Design

**Principle:** Importance is the filter. Relevance is the gate. Time is the sort. Count limits are forbidden.

| Importance | Meaning | Archive |
|-----------|---------|---------|
| 9 | Verified verdict — all agents read | Never |
| 7 | Librarian-indexed, significant | 90 days |
| 5 | Agent personal working notes | 60 days |
| 3 | Minimum query threshold | 30 days |
| 1–2 | Noise — excluded | Immediate |

Each agent has a personal pool (`memory_gemma`, `memory_llama`, etc.) plus access to the shared `memory` table for importance-9 verified verdicts.

---

## Platform Channels

| Channel | Entry Point | Notes |
|---------|------------|-------|
| Email | sevenpotato9@gmail.com | IMAP poll 60s → queue → ticket → agents → reply |
| Telegram | Fridays bot | Same pipeline as email |
| Discord DM | Fridays bot | 1900-char chunking, button interactions |
| Discord Notify | Channel 1486232966379343894 | Unknown sender, ticket open/close, SLA events |
| Terminal | Fridays UI port 5050 | Direct — bypasses queue, same ticket pipeline |
| Windows App | Fridays.exe (in development) | Native Edge WebView2, standalone .exe |

---

## Internet Access — Three Independent Paths

| Agent | Engine | Library |
|-------|--------|---------|
| LLaMA | DuckDuckGo | duckduckgo_search (no API key) |
| Mistral | Tavily AI | tavily-python |
| Qwen / Eighteen | Tavily AI (SAP-biased) | tavily-python |

When all three return the same answer, confidence is high.

---

## Ghost Circle

`claude_api.py` is the oversight layer. Gemma calls Claude (Nine) when genuinely stuck — last resort. All calls logged to `claude_log` and mirrored to `ghost_circle`. Never speaks directly to email senders.

---

## The Sandpit Model — Trust Ladder

```
/home/seven/swarm/sandpits/
├── shared/        — all agents read + write
├── gemma/
├── llama/
├── qwen/
├── qwen3.6/
├── mistral/
├── nine/
├── twelve/
└── sniffles/      — read-only (Level 0 only)
```

| Level | Access | Gate |
|-------|--------|------|
| 0 | Read-only everywhere | None |
| 1 | Own sandpit only | None |
| 2 | shared/proposals/ | Sniffles audits |
| 3 | System writes (approved paths) | Gemma approves |
| 4 | Shell execution (whitelist) | Ghost notified |
| 5 | Unrestricted | Ghost explicit sign-off |

---

## Phase History

| Phase | Name | Status |
|-------|------|--------|
| 1 | Foundation (email, memory, debate, Duck, Sniffles) | Done |
| 2 | Interface (terminal UI, search, routing) | Done |
| 3 | Fridays action (sandpits, browser, shell, skills) | Done |
| 4 | Platform (Telegram, Discord) | Done |
| 5 | Additional specialist agents | Backlog |
| 6 | Agent agency (proposals, KB docs, play time) | Done |
| 7 | Memory hardening, importance thresholds | Done |
| 8.0 | Agentic Chat | Done |
| A | File versioning | Done |
| B | System clock (centralised timestamps) | Done |
| C | Time Machine (point-in-time restore) | Backlog |
| D | UI/UX overhaul | Done |
| E | Access control expansion | Backlog |
| G | Frontend tile modularisation | In progress |
| H | Desktop application (Windows launcher) | In progress |
| I | Atmosphere Engine (time-of-day visual) | In progress |
| J | Enhanced Tasker & RAG | Done (Session 21) |

---

## Constraints That Must Never Be Broken

1. Gemma routes first — no web search before Gemma reads
2. Librarian only receives content to tag — never questions
3. Sniffles never interrupts active queue — waits 1+ hour of quiet
4. Duck runs after every ticket close, no exceptions
5. Ghost Circle never speaks directly to email senders
6. IS_IDENTITY=yes only for swarm/agent/Ghost questions
7. nvme0n1p1 (EFI) is untouchable
8. OLLAMA_HOST=0.0.0.0 always
9. config.py is never shared or printed
10. Ollama port 11434 — Tailscale only
11. Swarm Terminal port 5050 — Tailscale only
12. All timestamps via system_clock.py
13. Agents propose, Ghost approves — no agent action without sign-off
14. Memory limits set by importance, never by count
15. Play time fires at most once per agent per 24 hours
16. File versioning tracks all modifications with before/after content
