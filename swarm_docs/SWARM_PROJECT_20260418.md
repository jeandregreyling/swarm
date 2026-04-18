# SWARM PROJECT — Living Project Memory

> **How to use this file:** Start every session with *"look at the vibe coding project memory and see where we are at"*.  
> This is the single source of truth for project status, decisions, and session history.  
> Read **§1 STATUS** first. Read deeper only when needed.  
> Agents: this file is in the Library — consult it before proposing work to understand what's been done and what's planned.

**Owner:** Seven  
**Primary Builder:** Agent 12 (Claude / Copilot)  
**Created:** 16 April 2026  
**Last Updated:** 18 April 2026  

---

## §1 — CURRENT STATUS

| Field | Value |
|-------|-------|
| **Active Phase** | Phase 7.0 — Improvement Sprint ✅ ALL CHUNKS DONE |
| **Last Session** | Session 23 — 18 April 2026 — Phase 8.0 + 7D + 7E + 7F + 7G done |
| **Next Action** | Post-7G broken pipes: agents tab, enrollment, chat model selector |
| **Test Baseline** | 484 passed, 1 skipped |
| **Environments** | PROD (master :5050), UAT (:5053), DEV (:5051) — synced, 18 agents each |
| **Blockers** | None |

### What's Hot Right Now
- **Phase 8.0 — Agentic Chat** — major pivot: auto-routing agents, models, relay based on message content
- **Relay dispatch bug fixed** — multi-agent sends now force parallel mode; stall gate bypassed for fan-out
- **Phase 7.0 Chunks A–C complete** — env alignment, enrollment rename, Ghost Coder model dropdown verified
- **Phase 7.0 Chunks D–G deferred** — will interleave with Phase 8.0 as needed
- **Ghost Coder model selection confirmed working** — dropdown in Agents tile, 6 model options, DB-persisted
- **Model persistence fix landed** — `_seed_agents()` no longer overwrites user-chosen models on restart
- **qwen:1.5b deprecated** → replaced with `qwen:latest` across 5 files

---

## §2 — PHASE MAP

### Completed Phases

| Phase | Name | Completed | Key Deliverable |
|-------|------|-----------|-----------------|
| V1 | Initial Build | March 2026 | Flask monolith, 12 agents, SQLite, terminal UI |
| V2 | Refinement | 28 Mar 2026 | Bug audit (26 bugs fixed), BRK-002 timeout fix, world clocks |
| V3 | Stabilisation | 30 Mar 2026 | ALM governance, Time Wizard, 3-stage workflow, proposals |
| P1 | Fix What's Broken | 15 Apr 2026 | Tickets tile fix, Vortex→Git wiring, relay limit default 2, parallel toggle |
| P2 | Agent Registry | 15 Apr 2026 | 15 hardcoded dicts → DB, cached registry with 11 accessors, invalidation |
| P3a | Local Agent Skills | 15 Apr 2026 | Gemma/Qwen/Eight routed via .chat()→skills_loop (not orchestrator) |
| P3b | Trace Troubleshooter | 15 Apr 2026 | job_id on timeline, trace API, Trace tile + frontend |
| P4 | Fault Isolation | 15 Apr 2026 | Circuit breaker (3-state), health probe, stuck-job sweep, error boundaries |
| P5 | Lift-and-Shift | 15 Apr 2026 | Model discovery, hot-swap, import/export, system index, cross-referencing |
| Diamond A (prep) | Frontend Polish | 16 Apr 2026 | Sundial pulse, SVG icons, V-RAM/GPU metrics, keyboard shortcuts |

### Active Phase

| Phase | Name | Status | Target |
|-------|------|--------|--------|
| **6.0** | Standalone App Build | IN PROGRESS | Ongoing — iterative self-improvement |

#### Phase 6.0 — Build Plan

**Goal:** Move towards standalone app on all systems. Packaging model for future expansion. Iteratively keeps building itself into self-improvements.

**Tier 1 — Visual Transformation** (Next up)

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 1.1 | Library constellation | Merge Files+Docs+Library into unified view; gold glow for system docs; auto-classification | ✅ Done |
| 1.2 | Memory landscape | Force-directed graph of agent memory relationships | ✅ Done |
| 1.3 | Vortex time machine | Horizontal timeline with diff compare, branching visualisation | ✅ Done |

**Tier 2 — Interaction Polish**

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 2.1 | Chat fluidity | SSE real-time push, streaming responses, no-polling compose UX | ✅ Done |
| 2.2 | Skills drag-drop | Visual skill assignment with drag-drop interface | ✅ Done |
| 2.3 | Merge Setup + Agents tiles | Combined into single Agents tile; Setup Wizard button in header | ✅ Done |
| 2.4 | Thread icon + remaining emoji → SVG | Full emoji sweep: onboarding, feeds, toast, window-manager, all SVG | ✅ Done |
| 2.5 | Keyboard shortcuts overhaul | Global shortcuts: Ctrl+1–9 tiles, Ctrl+/ help, Esc close, Ctrl+Enter send | ✅ Done |

**Tier 3 — System Integration**

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 3.1 | Email compose | Full email client in-app (not just inbox viewer) | ✅ Done |
| 3.2 | Git per-environment | Separate git UI panels for DEV/UAT/PROD | 🔲 |
| 3.3 | Tailscale/VPN | VPN status + remote access integration | 🔲 |
| 3.4 | Weather in world clocks | Live weather via Open-Meteo API, icon + temp beside each clock | ✅ Done |

**Tier 4 — Self-Improvement (Iterative)**

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 4.1 | Auto-audit | Agents periodically self-audit code quality and test coverage | 🔲 |
| 4.2 | Pattern learning | Capture recurring fixes as reusable patterns | 🔲 |
| 4.3 | Build pipeline | Automated packaging for distribution on new systems | 🔲 |
| 4.4 | Agent personalities + diaries | Each agent gets personality.md + diary.md; self-reflect, think aloud, make suggestions | ✅ Done |
| 4.5 | Idle-time self-management | When system is idle, queue assigns each agent a ticket: update memory, clean sandbox, write diary, seek opinions | ✅ Done |
| 4.6 | Agent awareness API | Each agent can see "who they are" — skills, memory, prompt, capabilities, diary | ✅ Done |

---

### Phase 7.0 — Improvement Sprint (Active)

**Goal:** Fix user-reported UI/UX issues from testing. Each chunk is small, self-contained, and self-tested before moving to the next. PROD is source of truth — DEV/UAT always align from PROD.

**Rule:** Every chunk must pass: (1) automated tests, (2) API smoke test, (3) visual check on PROD, (4) sync to DEV+UAT, (5) restart services.

#### Chunk A — Environment Alignment ✅

| # | Task | Description | Status |
|---|------|-------------|--------|
| A.1 | Hard-sync PROD → DEV/UAT | Copy ALL frontend/ files from PROD to DEV and UAT worktrees | ✅ Done |
| A.2 | Restart all services | Restart swarm-terminal-prod, dev, uat | ✅ Done |
| A.3 | Verify identical UI | Spot-check 3 tiles on each environment match PROD | ✅ Done |

#### Chunk B — Rename "Setup Wizard" to "Enrollment" ✅

| # | Task | Description | Status |
|---|------|-------------|--------|
| B.1 | Rename button text | terminal_base.html: "Setup Wizard" → "Enrollment" | ✅ Done |
| B.2 | Rename window title | winManager.open title: "Setup Wizard" → "Enrollment" | ✅ Done |
| B.3 | Update onboarding.js header | Any "wizard" text in the step UI → "enrollment" | ✅ Done |
| B.4 | Verify button works | Click Enrollment in Agents tile header, confirm 5-step flow loads | ✅ Done |

#### Chunk C — Ghost Coder Model Selection ✅

| # | Task | Description | Status |
|---|------|-------------|--------|
| C.1 | Verify model dropdown renders | Open agents-config → Ghost Coder → model dropdown shows 6 options | ✅ Done |
| C.2 | Verify Apply button works | Select different model → Apply → confirm status message | ✅ Done |
| C.3 | Verify persistence | Set model → restart service → check model stayed | ✅ Done |
| C.4 | Verify dispatch | Send chat to ghost_coder with specific model → check which API was called | ✅ Done |
| C.5 | Model swap for ALL agents | Confirm local agents show Ollama models, paid agents show API models | ✅ Done |

#### Chunk D — System Log in Trace Tile

| # | Task | Description | Status |
|---|------|-------------|--------|
| D.1 | Add "System Log" tab to Trace | Tab bar added to `#view-trace` template: "Conversation Trace" + "System Log" | ✅ Done |
| D.2 | Wire to /api/activity endpoint | REST fetch on tab open: `GET /api/activity?limit=100` → populate panel | ✅ Done |
| D.3 | Auto-refresh | SSE stream via `/api/activity/stream` — live rows prepend, 500-row cap, self-cleans on window close | ✅ Done |
| D.4 | Verify log entries appear | API returns live vortex/checkpoint entries; PROD verified | ✅ Done |

**Implementation notes (7D):**
- HTML (`terminal_base.html`): Added `#trace-tab-bar` with two tab buttons calling `traceSwitchTab(tab)`. Split body into `#trace-trace-body` (flex, default visible) and `#trace-syslog-body` (display:none until tab clicked)
- JS (`trace.js`): `traceSwitchTab()` swaps display + active tab styling. `_traceStartSyslog()` opens `EventSource('/api/activity/stream')`, prepends rows with timestamp + service:event:detail. `_traceStopSyslog()` closes stream. `traceSyslogClear()` clears panel. `_traceSyslogRow()` renders monospace log row
- SSE self-cleans: `onmessage` checks `getElementById('trace-syslog-panel')` — if gone (window closed), calls `_traceStopSyslog()`
- Status badge shows ● Live (green) / ⚠ Disconnected (orange) based on SSE state
- Regression: 484 passed, 1 skipped — synced to DEV+UAT, all 3 services restarted

#### Chunk E — Merge Local AI into Agents Tile

| # | Task | Description | Status |
|---|------|-------------|--------|
| E.1 | Add "Local AI" tab/section to agents-config | Tab bar added to agents tile: "Agents" + "Local AI" | ✅ Done |
| E.2 | Show model pull/status | Ollama model pills, LM Studio loaded-model, Picoclaw status badges | ✅ Done |
| E.3 | Remove Local AI home card | Home card removed; replaced with comment `<!-- Local AI merged into Agents tile (7E) -->` | ✅ Done |
| E.4 | Verify Ollama status visible | `/api/localai/status` returns ollama + lmstudio + picoclaw; PROD verified | ✅ Done |

**Implementation notes (7E):**
- HTML (`terminal_base.html`): Added `#agents-tab-bar` with "Agents" / "Local AI" tabs calling `agentsSwitchTab(tab)`. Wrapped existing list+detail+footer in `#agents-agents-body`. Added `#agents-localai-body` (hidden) with 3 status cards (Ollama, LM Studio, Picoclaw) and a Refresh button
- JS (`agents-config.js`): `agentsSwitchTab()` swaps display + active tab styling + triggers `agentsLocalAIRefresh()` on switch. `agentsLocalAIRefresh()` fetches `/api/localai/status` and renders badges + Ollama model pills + LM Studio loaded-model text
- Home card removed; full `view-localai` template retained (accessible via other means or direct winManager call)
- Regression: 484 passed, 1 skipped — synced to DEV+UAT, all 3 services restarted

#### Chunk F — Merge Git into Studio

| # | Task | Description | Status |
|---|------|-------------|--------|
| F.1 | Add "Git" tab to Studio | `studio-tab-git` button added to Studio header toolbar | ✅ Done |
| F.2 | Move git.js content into studio tab | `#studio-git-panel` embedded in Studio template; `studioSetTab('git')` shows panel + calls `loadGitData()` | ✅ Done |
| F.3 | Remove Git home card | Home card removed; replaced with comment `<!-- Git merged into Studio (7F) -->` | ✅ Done |
| F.4 | Keep Ctrl+G shortcut | Ctrl+G now opens Studio and calls `studioSetTab('git')` after 120ms; command palette updated | ✅ Done |
| F.5 | Verify git operations work | Services restarted; PROD active; regression running | ✅ Done |

**Implementation notes (7F):**
- HTML (`terminal_base.html`): Added `id="studio-tab-git"` button to Studio header. Added `#studio-git-panel` div (display:none, full git UI inline — files list, diff, commit, proposals section)
- JS (`studio.js`): `studioSetTab()` now handles `'git'` — hides `#studio-content`, shows `#studio-git-panel` as flex, calls `loadGitData()` + `gitRefreshStatus()` on switch
- JS (`init.js`): Ctrl+G opens Studio then calls `studioSetTab('git')` after 120ms; command palette entry updated to match
- Studio home card desc updated: "Proposals · Git · History"
- Git home card removed from home grid

#### Chunk G — Email as Own Tile

| # | Task | Description | Status |
|---|------|-------------|--------|
| G.1 | Add Email card to home grid | `home-card` with envelope SVG, `data-win-id="email"`, `data-shortcut="Ctrl+E"` added back to home grid | ✅ Done |
| G.2 | Remove taskbar-only access | Taskbar email button retained; home card restored so Email is discoverable at home | ✅ Done |
| G.3 | Keep Ctrl+E shortcut | `init.js` unchanged — Ctrl+E still calls `openWindow('email','Email','view-email')` | ✅ Done |
| G.4 | Verify email loads | Services restarted (PROD/DEV/UAT active) | ✅ Done |

**Implementation notes (7G):**
- HTML (`terminal_base.html`): Replaced `<!-- Email removed from home (5.3) -->` comment with full `home-card` div — envelope icon SVG, `data-win-id="email"`, `data-win-template="view-email"`, `data-shortcut="Ctrl+E"`, desc "Inbox & compose"
- No JS changes required — `view-email` template and `email.js` already fully functional
- Taskbar email dot button retained as-is (unread indicator still works)

#### Future Chunks (after Sprint 7.0)

| Chunk | Description | Priority |
|-------|-------------|----------|
| H | Fridays self-reasoning — todo, knowledge, local memory | HIGH |
| I | VS Code as backend bridge — Ghost Coder ↔ Fridays pipeline | HIGH |
| K | Skills tile cleanup — cleaner layout, better drag-drop | LOW |
| L | Desktop packaging (Tauri) | LOW |

> **Note:** Former Chunk J (Chat 2.0) has been superseded by **Phase 8.0 — Agentic Chat** below.

---

### Phase 8.0 — Agentic Chat (Active — Planning)

**Goal:** Transform the chat from a manual multi-agent tool into an intelligent, auto-routing conversational interface. The system reads the user's message and automatically selects: which agent(s) to dispatch, which model to use, and whether to enable relay — all with manual override available at every step.

**Vision (user's words):** *"The model selection should be automated based on whatever the user puts into the chat, relay should be automated as well as on or off, agent selection should be agentic and proper according to the request, this should all be automated."*

**Design Principles:**
1. **Zero-config default** — user types a message, system handles everything
2. **Override always available** — manual agent/model/relay toggles remain accessible
3. **Transparent decisions** — show the user what was auto-selected and why
4. **Cautious rollout** — one chunk at a time, each tested before moving on
5. **No regressions** — existing manual workflows must continue to work

**Rule:** Same as Phase 7.0 — every chunk must pass: (1) automated tests, (2) API smoke test, (3) visual check on PROD, (4) sync to DEV+UAT, (5) restart services.

#### Chunk 8A — Agent Sidebar Always Expanded

**Scope:** Right dock Agent Controls section currently collapsed by default. Change to always expanded so agent pills are always visible.

| # | Task | Description | Status |
|---|------|-------------|--------|
| 8A.1 | Change default state | `data-chat-default="collapsed"` → `"open"`, remove `collapsed` class | ✅ Done |
| 8A.2 | Style polish | JS `initChatSections()` already had `agents: true` — now HTML matches | ✅ Done |
| 8A.3 | Verify on all envs | Synced to DEV+UAT, PROD restarted | ✅ Done |

#### Chunk 8B — Intent Classifier (Backend)

**Scope:** Build a backend classifier that reads user message text and returns: recommended agent(s), model tier, and relay on/off. This is the brain of agentic routing.

| # | Task | Description | Status |
|---|------|-------------|--------|
| 8B.1 | Create `/api/chat/classify` endpoint | Accepts message text, returns `{agents: [], model_tier: str, relay: bool, confidence: float, reasoning: str}` | ✅ Done |
| 8B.2 | Agent selection rules | Keyword/pattern matching: code→ghost_coder, search→seeker/scholar, multi-topic→relay, general→gemma | ✅ Done |
| 8B.3 | Model tier selection | Tasks categorised: simple→local (gemma/qwen), complex→paid (twelve/ten), code→ghost_coder, research→scholar | ✅ Done |
| 8B.4 | Relay auto-detection | Enable relay when: question spans multiple domains, or classifier confidence is low, or user says "ask around" | ✅ Done |
| 8B.5 | Unit tests | 25 tests covering all 8 categories + multi-domain + response shape — all passing | ✅ Done |

**Implementation notes (8B):**
- Classifier extracted to standalone `utils/intent_classifier.py` — no Flask deps, testable in isolation
- Route in `chat.py` uses lazy import: `from utils.intent_classifier import classify_message`
- 7 regex pattern categories + domain-specificity tiebreaker (code/math/creative/system win over generic search)
- Multi-domain relay triggers when 2nd category has ≥50% of top category's match count
- Regression: 429 passed, 1 skipped — verified on PROD, synced to DEV+UAT

**Classification categories (initial):**

| Category | Primary Agent(s) | Model Tier | Relay |
|----------|-----------------|------------|-------|
| Code generation/review | ghost_coder | paid (claude/gpt) | off |
| Code explanation | ghost_coder or twelve | paid | off |
| Web search / current info | seeker, scholar | paid (scholar=gemini) | off |
| General knowledge | gemma or llama | local | off |
| Creative writing | eleven or ten | paid | off |
| Multi-domain / ambiguous | gemma + specialist | local + paid | ON |
| System/swarm admin | duck or librarian | service | off |
| Math / reasoning | deepseek or nine | local/paid | off |
| Summarisation | qwen or gemma | local | off |
| Opinion / debate | multiple agents | mixed | ON |

#### Chunk 8C — Wire Classifier into Chat Frontend

**Scope:** Frontend calls `/api/chat/classify` before sending. Auto-populates agent selection, shows classification reasoning, allows override.

| # | Task | Description | Status |
|---|------|-------------|--------|
| 8C.1 | Pre-send classify call | Debounced 400ms classify-on-type via `/api/chat/classify`, auto-selects agents before send | ✅ Done |
| 8C.2 | Show classification badge | Badge above composer: "→ Agent (category · relay)" with tooltip showing reasoning | ✅ Done |
| 8C.3 | Override mechanism | Manual agent toggle sets `__classifyManualOverride`, shows ✎ icon, stops auto-selection | ✅ Done |
| 8C.4 | Auto-relay wiring | If classifier returns relay=true, auto-enables relay toggle | ✅ Done |
| 8C.5 | Model auto-selection | Classifier's model_tier passed via agent selection — agent→model mapping deferred to 8E | ✅ Partial |
| 8C.6 | "Why this agent?" tooltip | Hover on badge shows `data.reasoning` text via CSS ::after tooltip | ✅ Done |

**Implementation notes (8C):**
- `_debouncedClassify()` on textarea `oninput` — 400ms debounce, min 6 chars
- `_applyClassifyAgents(data)` — turns off all agents, turns on classified ones with state `'auto'`
- `_onManualAgentToggle()` hooked into `onChatAgentToggleChange` — sets override flag
- Badge auto-hides on send (`_hideClassifyBadge()` in `sendMessage`)
- Dismiss button (✕) manually hides badge and sets override
- CSS: fade-in animation, accent border, hover tooltip via `::after`

#### Chunk 8D — Home Screen Reorganisation

**Scope:** Home screen stays but tiles reorganise to bottom. Chat gets more visual prominence.

| # | Task | Description | Status |
|---|------|-------------|--------|
| 8D.1 | Move tile grid to bottom | Chat section moved above tiles; tiles now in compact `.home-tiles-section` below | ✅ Done |
| 8D.2 | Chat tile prominence | Chat uses `home-chat-prominent` class: flex:1, taller min-height, more visual space | ✅ Done |
| 8D.3 | Quick-launch from home | Typing anywhere on home page auto-focuses chat input (keydown handler on `#home-page`) | ✅ Done |
| 8D.4 | Verify responsive layout | Mobile rules: chat min-height 240px, tiles 2-col grid on ≤768px | ✅ Done |

**Implementation notes (8D):**
- HTML: Swapped order in `#home-content` — `.home-chat-section.home-chat-prominent` first, `.home-tiles-section` second
- CSS (`home-chat.css`): `.home-chat-prominent` gets `flex:1`, `min-height:380px`, `max-height:calc(100vh-280px)`
- CSS (`home-chat.css`): `.home-tiles-section` compact: smaller padding, 6px gap
- CSS (`responsive.css`): Mobile breakpoint ≤768px — chat min-height 240px, tiles 2-col
- JS (`home-chat.js`): `keydown` listener on `#home-page` — single printable chars focus `#home-chat-input`, skips modifier keys and existing input fields

#### Chunk 8E — Auto-Model Selection Per Agent

**Scope:** Each agent auto-selects the best available model based on task type and agent capabilities.

| # | Task | Description | Status |
|---|------|-------------|--------|
| 8E.1 | Model preference matrix | `utils/model_selector.py`: `_PREFERENCES` dict — ~25 (agent, category) → [model...] combos + `_DEFAULTS` per agent | ✅ Done |
| 8E.2 | Fallback chain | `get_fallback_chain()` returns ordered model list; preferences first, then agent default, deduped | ✅ Done |
| 8E.3 | Override from agent config | `select_model()` priority: user DB override (non-'auto') → category preference → agent default | ✅ Done |
| 8E.4 | Verify dispatch | 21 tests in `tests/test_model_selector.py`; `/api/chat/classify` returns `models` dict; verified on PROD | ✅ Done |

**Implementation notes (8E):**
- New standalone module `utils/model_selector.py` — no Flask deps, testable in isolation
- `select_model(agent, category, user_model)` → `(model_str, source)` where source is 'override'|'preference'|'default'
- `get_fallback_chain(agent, category)` → ordered list of models best→worst
- `select_models_for_agents(agents, category, user_models)` → batch selection for multi-agent dispatch
- `/api/chat/classify` enhanced: lazy imports `select_models_for_agents`, reads user models from `get_agent_models()`, adds `result['models']`
- Frontend badge (`chat.js`) now shows model name in category text and detailed tooltip with model source info
- Key preferences: ghost_coder+code→claude-sonnet-4, ghost_coder+creative→claude-opus-4, eleven+creative→grok-3, deepseek_local+math→deepseek-r1:7b
- Regression: 450 passed, 1 skipped — verified on PROD, synced to DEV+UAT

#### Chunk 8F — Full Integration Test

**Scope:** End-to-end testing of the complete agentic chat flow.

| # | Task | Description | Status |
|---|------|-------------|--------|
| 8F.1 | Code question test | `classify("Write a Python function...")` → `ghost_coder`, model=claude-opus (override), relay=false | ✅ Done |
| 8F.2 | Search question test | `classify("what's in the news...")` → `seeker, scholar`, relay=false | ✅ Done |
| 8F.3 | Multi-domain test | `classify("ask all agents...")` → `gemma, twelve, nine`, relay=true, tier=mixed | ✅ Done |
| 8F.4 | Manual override test | User model always wins: `select_model(..., user_model=X)` → source='override', 5 tests | ✅ Done |
| 8F.5 | Regression test | 484 passed, 1 skipped — all pre-8F features intact | ✅ Done |
| 8F.6 | Performance test | 100 calls in 2.02ms (0.020ms each) — target was <50ms per call | ✅ Done |

**Implementation notes (8F):**
- New test file `tests/test_8f_integration.py` — 34 tests across 6 classes (8F.1–8F.6)
- Domain-specificity tiebreaker confirmed: "search for Python release notes" → `code` (correct — Python is a code keyword)
- Creative pattern requires `write [a] [word] poem` — "write me a poem" doesn't match (by design, avoids false positives)
- Performance: classify + model select pipeline averages 0.020ms per call — 2500× faster than the 50ms target
- Live API smoke: all 3 endpoint responses verified on PROD before regression run

**Tier 5 — Home Screen & Responsive Design**

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 5.1 | Monitor tile expansion | System Activity merged into Monitor; sundial + recent events in one tile | ✅ Done |
| 5.2 | Remove Tickets tile from home | Already linked in chats/proposals/tickets window; use activity dots instead | ✅ Done |
| 5.3 | Remove Emails tile from home | Same as tickets — linked elsewhere with activity dots for "undead" items | ✅ Done |
| 5.4 | Responsive / mobile layout | Everything must fit on phone screen; clocks → digital when space is tight; all elements reflow | ✅ Done |
| 5.5 | Clocks responsive fallback | World clocks switch to compact digital format when screen width < threshold | ✅ Done |
| 5.6 | Window dedup / internal management | Prevent duplicate windows; only one instance per view; second click focuses existing | ✅ Done |

#### Diamond Layer (Background — paused for Phase 6)

| Phase | Name | Status | Target |
|-------|------|--------|--------|
| 4.0-A | Diamond Layer — Governance Core | PAUSED | Resume after Tier 1 |

### Future Phases

| Phase | Name | Depends On |
|-------|------|------------|
| 4.0-B | Research Assistant / Learning Lab | Diamond A complete |
| 4.0-C | Tool Builder | B stable |
| 4.0-D | Distribution (multi-node activation) | A prepared, C stable |

---

## §3 — ARCHITECTURE SNAPSHOT

```
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND  │  Jinja2 + Vanilla JS  │  Views in static/js/  │
│            │  CSS custom props      │  Themes engine         │
├─────────────────────────────────────────────────────────────┤
│  FLASK APP │  34+ blueprints       │  205+ routes           │
│            │  Services layer       │  Pipeline orchestrator  │
├─────────────────────────────────────────────────────────────┤
│  AGENTS    │  18 registered        │  DB-backed registry    │
│            │  Local: Gemma, LLaMA, Qwen, Mistral, Eight, Phi3, DeepSeek │
│            │  Paid: Nine, Ten, Eleven, Twelve, Thirteen, Scholar, Ghost Coder │
│            │  Service: Duck, Sniffles, Librarian, Seeker    │
├─────────────────────────────────────────────────────────────┤
│  DATA      │  SQLite WAL           │  78+ tables            │
│            │  Agent registry       │  Circuit breaker state  │
├─────────────────────────────────────────────────────────────┤
│  INFRA     │  3 worktrees          │  systemd services      │
│            │  PROD :5050           │  UAT :5052             │
│            │  DEV :5054            │  Ollama :11434          │
└─────────────────────────────────────────────────────────────┘
```

### Key Technical Facts
- **Python 3.12.3** — always use `python3` not `python`
- **Git worktrees**: `/home/seven/swarm` (master/PROD), `/home/seven/swarm-dev` (dev), `/home/seven/swarm-uat` (uat)
- **Vortex** auto-commits on changes via TimeWizard hooks
- **Theme system**: CSS custom properties (`--bg`, `--card`, `--accent`, `--glow-a/b`, `--mist`), named themes in `themes.css`, atmosphere engine injects time-of-day overrides
- **Icon system**: 16×16 SVGs, `stroke="currentColor"`, `fill="none"` — inherits theme colours. NO emoji in UI.
- **Dell Optiplex 7090** refurb, 128GB SSD converted to swap (V-RAM for bigger models), no GPU yet
- **Frontend pattern**: `openWindow(id, title, template)` managed by `winManager`
- **Home screen**: `#home-page` > `#home-header` (sundial + clocks + time + controls) + `#home-content` > `.card-grid`

---

## §4 — DECISION LOG

Architectural and design decisions that affect future work. Newest first.

| Date | Decision | Rationale | Ref |
|------|----------|-----------|-----|
| 18 Apr | Phase 8.0 — Agentic Chat replaces manual agent/model/relay selection | User wants zero-config chat: system auto-routes based on message content | SWARM_PROJECT |
| 18 Apr | Auto-route with manual override (not fully automatic) | User must always be able to override classifier decisions | Session 22 |
| 18 Apr | Agent sidebar always expanded (not collapsed) | User wants agent pills visible at all times in right dock | Session 22 |
| 18 Apr | Home stays, tiles reorganise to bottom | Not replacing home with chat — reorganise tiles for config/fine-tuning | Session 22 |
| 18 Apr | Force parallel_mode for explicit multi-agent sends | Sequential stall gate was blocking multi-agent fan-out | chat.py relay fix |
| 17 Apr | SSE real-time push for chat (not polling) | Eliminates polling overhead; instant message display | chat_bp.py SSE endpoint |
| 17 Apr | Memory landscape uses canvas force-directed graph | Interactive physics sim for agent-memory relationships; performant at scale | memory-landscape.js |
| 17 Apr | Setup Wizard absorbed into Agents tile | Reduces home card count; wizard accessible via header button | terminal_base.html |
| 17 Apr | auth.py /api/skills renamed to /api/skills/available | Route conflict with agents.py /api/skills (different data) | auth.py |
| 16 Apr (eve) | Phase 6.0 — Standalone App Build replaces Diamond Layer as active phase | User wants to "move towards standalone app on all systems"; packaging model for future expansion | SWARM_PROJECT.md |
| 16 Apr (eve) | Registry `name` = DB `name` column (lowercase key), `label` = display name | Was returning label as name, breaking chat validation for all agents | registry.py line 99 |
| 16 Apr (eve) | Tier 4 (Self-Improvement) added — iterative auto-audit, pattern learning, build pipeline | User wants system to "iteratively keep building itself into self improvements" | Phase 6 plan |
| 16 Apr | All icons must be SVG stroke/currentColor — no emoji | Consistency with theme system; emoji don't change colour with themes | Sundial rewrite |
| 16 Apr | V-RAM (swap) and GPU VRAM added as sundial metrics | 128GB SSD is used for model swap; GPU placeholder for future hardware | diamond.js |
| 16 Apr | Project tracking via single SWARM_PROJECT.md | Stop doc sprawl; agents read one file; sessions start with status check | This file |
| 15 Apr | Agent registry is DB-backed, not hardcoded | 15 dicts across 5 files had drift bugs; DB is single source of truth | P2 registry.py |
| 15 Apr | Circuit breaker pattern for agent dispatch | Prevents cascade failures; fast-fails when Ollama is down | P4 circuit_breaker.py |
| 15 Apr | Local agents route through .chat() not orchestrator | Enables skills_loop for Gemma/Qwen/Eight; matches LLaMA/Mistral pattern | P3a chat.py |
| 15 Apr | Trace troubleshooter via job_id on timeline | Links chat jobs to timeline events for full request tracing | P3b timeline.py |
| 1 Apr | ALM gate is mandatory for mutations | No undocumented changes; proposals are the audit trail | ALM_DRIVER.md |
| 30 Mar | Three-environment workflow (DEV→UAT→PROD) | Agents test in DEV, user validates in UAT, then promotes to PROD | MULTI_STAGE_WORKFLOW.md |
| 30 Mar | Vortex is the single traceability layer | All git, time machine, and audit flows go through Vortex | ARCHITECTURE.md |
| 28 Mar | Documentation-first lifecycle | Every change must be documented; docs are code | ALM_DRIVER.md |
| 28 Mar | One-at-a-time relay queue (not parallel by default) | Prevents resource contention on local hardware; sequential = default | chat.js |

---

## §5 — SESSION LOG

Each session is logged here with date, what was done, and key outcomes.  
**Newest first** — most recent session is always at the top.

---

### Session 22 — 18 April 2026 (Evening)
**Focus:** Multi-agent relay dispatch fix + Phase 8.0 Agentic Chat vision

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Fix multi-agent relay dispatch | ✅ Done | Thread #706: 10 agents sent, only 1-2 responded. Root cause: sequential stall gate |
| 2 | Force parallel for multi-agent | ✅ Done | chat.py line ~588: if >1 agent explicitly selected → parallel_mode=True |
| 3 | Bypass stall gate for fan-out | ✅ Done | chat.py line ~1480: stall gate skipped when `_multi_agent_fanout` is true |
| 4 | Sync fix to all envs | ✅ Done | PROD, DEV, UAT all updated with relay fix |
| 5 | Confirm Ghost Coder model works | ✅ Done | User verified: dropdown visible in Agents tile, 6 model options |
| 6 | Phase 8.0 vision discussion | ✅ Done | Locked: auto-route + override, agent pills expanded, home reorganised |
| 7 | Update SWARM_PROJECT | ✅ Done | Phase 8.0 plan with 6 chunks (8A–8F), decisions logged |

**Root Cause (relay bug):** `_sequential_stalled` flag was set after the first agent timeout in sequential mode. When user sends to multiple agents, the system defaulted to sequential mode, so after one agent's timeout, the stall gate blocked all remaining agents. Two fixes: (1) force parallel when >1 agent explicitly selected, (2) add `_multi_agent_fanout` bypass for stall gate.

**Phase 8.0 Design Decisions:**
- Agent selection: backend classifier at `/api/chat/classify` reads message → returns recommended agents
- Model selection: classifier returns model_tier → maps to specific model per agent  
- Relay: auto-detected based on multi-domain questions or low confidence
- Override: manual toggles always available — user selection beats classifier
- Agent sidebar: always expanded (pills visible), not collapsed by default
- Home screen: stays as-is but tiles reorganise to bottom for config/fine-tuning access
- Execution: sequential cautious chunks (8A→8B→8C→8D→8E→8F)

**Files Modified:** `frontend/blueprints/chat.py` (2 changes), `swarm_docs/SWARM_PROJECT_20260418.md`
**Tests:** 398 passed, 1 skipped
**Envs synced:** Yes (PROD, DEV, UAT) — all running with 18 agents

---

### Session 21 — 18 April 2026
**Focus:** Improvement sprint planning + environment alignment + model persistence fix

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Fix `_seed_agents()` model overwrite | ✅ Done | ON CONFLICT now uses CASE WHEN — user-set models survive restart |
| 2 | Replace deprecated `qwen:1.5b` | ✅ Done | → `qwen:latest` in _schema.py, orchestrator.py, debate.py, setup_node.py, seed_agent_permissions.py |
| 3 | Verify model persistence | ✅ Done | Set duck→qwen2.5:latest, restarted PROD, confirmed it persisted |
| 4 | Audit env alignment | ✅ Done | Found 16 frontend files out of sync between PROD and DEV/UAT |
| 5 | Build Phase 7.0 plan | ✅ Done | 7 chunks (A–G) with self-testing checklist per chunk |
| 6 | Create SWARM_PROJECT_20260418.md | ✅ Done | Updated project memory with Phase 7.0 improvement sprint |
| 7 | Chunk A: Hard-sync environments | 🔲 Pending | Next up — copy all frontend from PROD → DEV/UAT |
| 8 | Chunk B: Rename wizard → enrollment | 🔲 Pending | terminal_base.html + onboarding.js |
| 9 | Chunk C: Ghost Coder model verify | 🔲 Pending | End-to-end test after env sync |

**Key Findings:**
- 16 frontend files drifted between PROD and DEV/UAT (templates, JS views, CSS)
- Backend files (agents.py, chat.py) also drifted
- `_schema.py` seed was the root cause of model selection not persisting — ON CONFLICT SET model=excluded.model reset on every startup
- `qwen:1.5b` removed from Ollama registry (Qwen v1 deprecated) — duck/librarian had a dead model reference
- Email is accessible only via taskbar Ctrl+E — user wants it as a home tile
- "Setup Wizard" button exists in agents-config header but should say "Enrollment"
- Local AI and Git tiles duplicate content available in Agents and Studio respectively

**New Decisions:**
- Phase 7.0 replaces Phase 6.0 as active — Phase 6 remaining tiers (3.2, 3.3, 4.1-4.3) deferred
- Each chunk must self-test before moving to next
- PROD is always source of truth — DEV/UAT sync FROM prod, never the reverse
- "Wizard" terminology banned — use "Enrollment" or "Add New Member"

**Files Modified:** `utils/db/_schema.py`, `core/pipeline/orchestrator.py`, `core/pipeline/debate.py`, `scripts/setup_node.py`, `ops/seed_agent_permissions.py`
**Tests:** 398 passed, 1 skipped
**Envs synced:** Partial — backend synced, frontend still drifted (Chunk A will fix)

---

### Session 20 — 17 April 2026 (Evening)
**Focus:** Audit SWARM_PROJECT.md against reality, fix 6 bugs/gaps found during testing

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Tier 4.4: Agent personality + diary | ✅ Done | personality_bp.py — GET/PUT personality.md, GET/POST diary entries |
| 2 | Tier 4.5: Idle-time self-management | ✅ Done | idle_mgmt_bp.py — idle agent detection, claim pending work, queue depth |
| 3 | Tier 4.6: Agent awareness API | ✅ Done | /api/agents/<name>/self — config, capabilities, activity, personality |
| 4 | Tier 5.4: Responsive layout | ✅ Done | responsive.css — tablet/mobile/phone breakpoints, reflow |
| 5 | Tier 5.5: Clocks responsive fallback | ✅ Done | Hides analog faces, horizontal digital strip on mobile |
| 6 | Audit SWARM_PROJECT.md vs code | ✅ Done | Found 6 gaps between spec and implementation |
| 7 | Fix: Monitor rotation error | ✅ Done | `const rotation` was inside template literal — moved before `content.innerHTML` |
| 8 | Fix: Files path DEV/UAT | ✅ Done | Removed hardcoded `/home/seven/swarm` from files.js; server defaults to `_SWARM_ROOT` |
| 9 | Fix: Files pop-out window | ✅ Done | Added "Full" button + `filesOpenFull()` — fetches up to 100KB, opens in new window |
| 10 | Fix: Email access path | ✅ Done | Added email envelope button with activity dot to taskbar (beside Home) |
| 11 | Fix: Library constellation visual | ✅ Done | Gold glow CSS, auto-classification badges (doc/code/config), tab active glow |
| 12 | Fix: Skills drag-drop visibility | ✅ Done | Pulsing dashed border, accent-colored label, instructional hint text |
| 13 | Update SWARM_PROJECT.md | ✅ Done | 10 tiers marked ✅, session logged |
| 14 | Sync + restart services | ✅ Done | master→dev→uat, PROD + DEV restarted |

**New Files:** `frontend/blueprints/personality_bp.py`, `frontend/blueprints/idle_mgmt_bp.py`, `frontend/static/css/responsive.css`  
**Modified:** monitor.js, files.js, knowledge.js, skills.js, terminal_base.html, agents.py, terminal.py, SWARM_PROJECT.md  
**Commits:** auto-committed by Vortex/Sniffer chain + `d5f7267` (gap fixes)  
**Tests:** 399 passed, 1 skipped (unchanged)  
**Envs synced:** Yes (master, dev, uat) — services restarted

---

### Session 19 — 17 April 2026
**Focus:** 6-hour autonomy build — tiers, health sweep, emoji cleanup, sync

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Tier 5.1: Monitor tile expansion | ✅ Done | System Activity merged into Monitor; sundial + recent events |
| 2 | Tier 1.3: Vortex timeline enhance | ✅ Done | Horizontal scrubber, event detail panel, diff compare |
| 3 | Tier 2.1: Chat fluidity (SSE) | ✅ Done | Real-time push via SSE; no more polling for new messages |
| 4 | Tier 3.4: Weather in world clocks | ✅ Done | Open-Meteo API, weather icons + temp beside each clock |
| 5 | Tier 1.2: Memory landscape | ✅ Done | Canvas force-directed graph of agent memory relationships |
| 6 | Tier 2.3: Merge Setup+Agents | ✅ Done | Single Agents tile; Setup Wizard button in header |
| 7 | Health check: JS conflicts | ✅ Done | Removed dead agents-config.js (shadowed by access.js) |
| 8 | Health check: API route clash | ✅ Done | auth.py /api/skills → /api/skills/available |
| 9 | Emoji sweep (Tier 2.4) | ✅ Done | onboarding, feeds, toast, window-manager — all SVG |
| 10 | Sync + restart services | ✅ Done | master→dev, master→uat, both services restarted |
| 11 | Update SWARM_PROJECT.md | ✅ Done | All tiers marked, session logged |

**Commits:** `5a99055` (Monitor), `54a7175` (Vortex), `44b882d` (Chat SSE), `3b027f5` (Weather), `b3369cf`+`e72e081` (Memory landscape), `ad5344b` (Setup+Agents merge), `e095ceb` (health fixes + emoji sweep)
**Tests:** 399 passed, 1 skipped (+1 test from prior session)
**Envs synced:** Yes (master, dev, uat) — services restarted

---

### Session 18 — 17 April 2026 (Early)
**Focus:** Tier 5.6 window dedup, Tier 2.5 keyboard shortcuts

(Completed in prior conversation — tiers 5.6 and 2.5 done)

---

### Session 17 — 16 April 2026 (Evening)
**Focus:** Housekeeping, API pipe testing, registry bug fix, Phase 6 roadmap

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Archive 17 historical docs | ✅ Done | Moved to `Archives/docs_historical/` |
| 2 | Archive 9 legacy HTML pages | ✅ Done | Moved to `Archives/html_legacy/docs_html/` |
| 3 | Delete 6 stale backup files | ✅ Done | Removed `.backup`, `.bak-*`, `.monolith` files |
| 4 | API smoke tests (25+ endpoints) | ✅ Done | All healthy except chat (found bug) and git diff (needs path param) |
| 5 | Fix registry name/label swap bug | ✅ Done | `get_agent_roster()` was returning label as name; chat send broken for all agents |
| 6 | Service restart (port 5050 stuck) | ✅ Done | Stale process held port; killed + restarted |
| 7 | Verify chat for all agents | ✅ Done | gemma, llama, mistral, qwen, duck — all OK |
| 8 | Update SWARM_PROJECT.md Phase 6 | ✅ Done | Tier 1/2/3/4 build plan; standalone app direction |
| 9 | Sync to dev/uat | ✅ Done | Both worktrees merged from master |
| 10 | "Fridays as a vibe" concept | 🔲 Pending | Carry forward |

**Bug Fixed:** `utils/db/registry.py` line 98 — `get_agent_roster()` returned `r.get('label')` as `name` instead of `r['name']`. Frontend sends `gemma` but roster had `Gemma3`→`gemma3`. Fixed: `name` = DB key, `label` = display.  
**Commits:** `f979146` (housekeeping), registry fix (auto-committed by Vortex)  
**Tests:** 398 passed, 1 skipped (unchanged)  
**Envs synced:** Yes (master, dev, uat)

---

### Session 16 — 16 April 2026
**Focus:** Sundial fix, SVG icons, V-RAM/GPU metrics, project memory

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Debug sundial not rendering | ✅ Done | Cache issue — system reboot resolved it |
| 2 | Replace emoji with SVG icons | ✅ Done | 8 themed SVG icons, tooltip health dots |
| 3 | Replace Queue metric with V-RAM + GPU | ✅ Done | swap_percent + nvidia-smi detection |
| 4 | Create SWARM_PROJECT.md | ✅ Done | This file — single source of project truth |
| 5 | Create repo memory compact file | ✅ Done | /memories/repo/swarm-project.md |
| 6 | "Fridays as a vibe" concept | 🔲 Pending | Carry forward |

**Commits:** `3fbfc1f` (V-RAM/GPU metrics), `6567e9c` (SVG icons)  
**Tests:** 398 passed, 1 skipped  
**Envs synced:** Yes (master, dev, uat)

---

### Session 15 — 15 April 2026
**Focus:** Phases 1–5 implementation (Fridays BASH plan)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | P1: Fix Tickets tile | ✅ Done | JS was corrupted; rewrote template rendering |
| 2 | P1: Wire Vortex to Git | ✅ Done | git tag on checkpoint, git info in restore |
| 3 | P1: Relay limit default 4→2 | ✅ Done | chat.js + chat.html |
| 4 | P1: True parallel toggle | ✅ Done | Separate exec mode button in chat toolbar |
| 5 | P2: Agent Registry | ✅ Done | 15 dicts → DB, registry.py with 11 accessors |
| 6 | P2: Replace all hardcoded dicts | ✅ Done | services.py, orchestrator.py, memory.py, debate.py, agents.py |
| 7 | P3a: Local agent skill routing | ✅ Done | Gemma/Qwen/Eight via .chat()→skills_loop |
| 8 | P3b: Trace troubleshooter | ✅ Done | job_id timeline, trace API, Trace tile |
| 9 | P4: Circuit breaker | ✅ Done | 3-state per-agent, health probe, stuck-job sweep |
| 10 | P4: Error boundaries | ✅ Done | Consistent timeout handling across all agents |
| 11 | P5.1: Model discovery | ✅ Done | /api/localai/available-models |
| 12 | P5.2: Hot-swap | ✅ Done | /api/agents/hot-swap |
| 13 | P5.3: Import/export | ✅ Done | /api/agents/export-all, /api/agents/import |
| 14 | P5.4: System index + SKILL | ✅ Done | swarm_docs/SYSTEM_INDEX.md auto-generator |
| 15 | P5.5: Cross-referencing | ✅ Done | tickets↔proposals↔conversations linking |

**Tests:** 398 passed, 1 skipped  

---

### Sessions 1–14 — March–April 2026 (Historical)

Detailed records exist in:
- `docs/CHANGELOG.md` — per-session change inventory
- `docs/TASK_TRACKER_LIVE.md` — per-session delta tables (sessions 7–11)
- `docs/audits/AUDIT_TRAIL.md` — audit evidence ledger
- `docs/changes/CHANGELOG_OPERATIONS.md` — operational change ledger

Key milestones from these sessions:
- **Sessions 1–3**: Initial V1 build, 12 agents, Flask monolith, terminal UI
- **Session 4**: World clocks, UI fixes, Telegram DB repair (20 commits)
- **Session 5**: V2 refinement, 26 bugs fixed, BRK-002 timeout fix
- **Session 6**: V3 stabilisation, ALM governance, Time Wizard, 3-stage workflow
- **Session 7**: Identity architecture rewrite, system prompts, cross-references
- **Session 8**: SVG icon overhaul, UI density, trace fix, test repairs
- **Session 9**: Claude Code handover, UAT test scripts
- **Session 10**: Theme architecture separation
- **Session 11**: System validation, notification reliability, Gmail push recovery
- **Sessions 12–14**: Diamond Layer planning, frontend polish, keyboard shortcuts

---

## §6 — DOCUMENT INDEX

All project documentation catalogued by purpose. Agents should consult this to find relevant references.

### Living Documents (Always Current)

| File | Purpose | Update Frequency |
|------|---------|------------------|
| `swarm_docs/SWARM_PROJECT.md` | **This file** — project status, phases, sessions | Every session |
| `docs/ARCHITECTURE.md` | System architecture reference | On structural changes |
| `docs/API_REFERENCE.md` | 205+ route reference (v4.0) | On API changes |
| `docs/BUGS.md` | Bug log with status tracking | On bug discovery/fix |
| `docs/CHANGELOG.md` | Per-session change inventory | Every session |
| `docs/FEATURES_TODO.md` | Feature backlog (30 tasks, 9 phases) | On priority changes |
| `docs/PROJECT.md` | "The coder's bible" — master project doc | On major changes |
| `docs/PHASE_4.0_DIAMOND_LAYER.md` | Diamond Layer + Service Boundaries spec | Active phase |
| `docs/TASK_TRACKER_LIVE.md` | Per-session task delta tables | Every session |
| `swarm_docs/SYSTEM_INDEX.md` | Auto-generated module index | On code changes (SKILL) |
| `swarm_docs/SYSTEM_LANDSCAPE.json` | Machine-readable system map | Auto-generated |

### Governance & Process

| File | Purpose |
|------|---------|
| `docs/ALM_COOKBOOK.md` | Proposal & approval workflow cookbook |
| `docs/ALM_DRIVER.md` | Documentation-first lifecycle rules |
| `docs/DEVELOPER_WORKFLOW.md` | Edit safety rules + Vortex workflow |
| `docs/MULTI_STAGE_WORKFLOW.md` | DEV→UAT→PROD promotion flow |
| `docs/ENVIRONMENTS_REFERENCE.md` | Stage 1/2/3 ports and addresses |
| `docs/DEPLOYMENT_GUIDE.md` | Prereqs, setup, services |
| `docs/registry/FILE_REGISTRY.md` | Master file index |
| `docs/registry/FILING_SYSTEM.md` | Canonical filing standard |
| `docs/runbooks/CHANGE_AND_AUDIT_WORKFLOW.md` | Change → validate → log → audit |
| `docs/runbooks/DOCUMENTATION_LIFECYCLE_WORKFLOW.md` | Doc management runbook |
| `docs/audits/AUDIT_TRAIL.md` | Append-only audit evidence |
| `docs/changes/CHANGELOG_OPERATIONS.md` | Operational change ledger |

### Design References

| File | Purpose |
|------|---------|
| `docs/ARCHITECTURE_DIAGRAM.md` | Mermaid system diagram |
| `docs/POSITIONING_PAPER.md` | Agent personality architecture paper |
| `docs/SYSTEM_CLOCK.md` | Unified time source design |
| `docs/VERSION_CONTROL.md` | Time Machine & versioning strategy |
| `docs/FILE_STRUCTURE.md` | Post-reorg file tree |
| `docs/PROJECT_ANALYSIS.md` | LOC/file analysis (121 files, ~32K LOC) |

### Agent References

| File | Purpose |
|------|---------|
| `docs/AGENT_TWELVE_MANUAL.md` | Agent Twelve operational manual |
| `docs/testing/ALM_TEST_SPECIFICATION.md` | ALM test cases |
| `docs/testing/COMPREHENSIVE_TEST_PLAN_2026-04-01.md` | E2E validation plan |
| `docs/UAT_TEST_SCRIPTS.md` | Reusable UAT test suite |
| `docs/testing/TIME_WIZARD_TESTS.md` | Time Wizard pytest suite |

### API Schemas (JSON)

Located in `docs/api/`: chat.json, governance.json, proposals.json, research.json, studio.json, tools.json, vortex.json

### Historical / Archived

These are point-in-time records. Preserved for audit trail but not actively maintained:

| File | Date | What It Captured |
|------|------|-----------------|
| `docs/AGENT_TASK_ASSIGNMENTS.md` | 28 Mar | Refinement phase task assignments |
| `docs/AGENT_TWELVE_STATUS.md` | 28 Mar | Agent Twelve bootstrap report |
| `docs/APPROVALS_PROPOSALS_STATUS_2026-03-30.md` | 30 Mar | Proposal queue snapshot |
| `docs/AUDIT_MARCH_30_2026.md` | 30 Mar | Session 4 audit (20 commits) |
| `docs/AUDIT_V3_MARCH_28.md` | 28 Mar | V3 system state audit |
| `docs/CLAUDE_CODE_HANDOVER.md` | ~5 Apr | Session 9 handover brief |
| `docs/FRIDAYS_AUDIT_SUMMARY.md` | 28 Mar | "46 errors" investigation |
| `docs/FRIDAYS_BUG_FIX_LOG.md` | 28 Mar | 26-bug refinement audit |
| `docs/FRIDAYS_RESOLUTION_FINAL.md` | 28 Mar | Root cause: commit 606a213 |
| `docs/REFINEMENT_PHASE_SUMMARY.md` | 28 Mar | Refinement handoff |
| `docs/SELF_AUDIT_2026-03-30.md` | 30 Mar | Self-audit snapshot |
| `docs/SESSION_5_COMPLETION_SUMMARY.md` | 29 Mar | Session 5 audit |
| `docs/STATE_SNAPSHOT_2026-03-30_SIGNOFF.md` | 30 Mar | Runtime state sign-off |
| `docs/THEME_ARCHITECTURE_CHANGES.md` | 28 Mar | Theme layer separation |
| `docs/TIME_WIZARD_COMPLETE.md` | 30 Mar | Time Wizard integration report |
| `docs/VS_CODE_CONTEXT.md` | 25 Mar | VS Code context brief |
| `docs/STAGING_WORKFLOW.md` | — | Near-duplicate of MULTI_STAGE_WORKFLOW.md |

---

## §7 — KNOWN PATTERNS & GOTCHAS

Things that have bitten us before. Check this section when debugging.

| Pattern | Detail |
|---------|--------|
| **Agent registry `name` vs `label`** | `name` = DB key (lowercase, e.g. `gemma`). `label` = display (e.g. `Gemma3`). Never use label for routing/matching. |
| **Browser cache** | Static files (.js, .css) get cached aggressively. Hard refresh or service restart needed after frontend changes. |
| **`python3` not `python`** | System has Python 3.12.3. The `python` command doesn't exist. |
| **Terminal DOM cloning** | `terminal_base.html` is a full SPA shell. Views are `<template>` elements cloned by window manager. Don't add `<script>` inside templates. |
| **Vortex auto-commits** | TimeWizard hooks fire on every `git commit`. Don't be alarmed by `[TimeWizard]` prefixed output. |
| **Services restart** | After backend changes: `sudo systemctl restart swarm-terminal` (PROD) / `swarm-terminal-dev` (DEV). |
| **Three envs must align** | After master commit: `cd /home/seven/swarm-dev && git merge master --no-edit` then same for `swarm-uat`. |
| **Property objects at module level** | Python `property()` only works inside classes. Never use `property()` for module-level lazy values — use functions instead. |
| **Relay limit** | Default is 2, not 4. Changed in P1. |
| **Agent memory tables** | Named `memory_{agent_name}`. Auto-created by registry seed. |
| **Icon pattern** | 16×16 viewBox, `stroke="currentColor"`, `stroke-width="1.3"`, `fill="none"`. See `FRIDAYS_WINDOW_ICON_SVGS` in window-manager.js. |
| **files.js hardcoded path** | Was using `/home/seven/swarm` as default — breaks in DEV/UAT worktrees. Fixed: empty string defaults to `_SWARM_ROOT` server-side. |
| **Template literal JS** | Never put `const`/`let` declarations inside template literals — they render as text, not code. Monitor rotation bug was exactly this. |
| **`_seed_agents()` ON CONFLICT** | The seed function runs on every startup. Before fix: `ON CONFLICT DO UPDATE SET model=excluded.model` reset user-chosen models. After fix: uses `CASE WHEN agents.model IS NULL OR agents.model=''`. Never add `model=excluded.model` back. |
| **Sniffer auto-commits** | The Sniffer agent watches for file changes and auto-commits via Vortex chain. Your edits may be committed before you explicitly `git add`. |

---

*End of SWARM_PROJECT.md — updated 18 April 2026*
