# Nine — Decision Index

**Agent**: Nine (System Architect · Ghost Layer)
**Last Updated**: 2026-03-29
**Numbering**: NINE-XXX (separate from Twelve's DECISION-XXX)

---

## Active Proposals — Awaiting Ghost Approval

| ID | Title | Priority | Status | Proposal File |
|----|-------|----------|--------|---------------|
| NINE-001 | File path bugs — PROJECT.md, UAT, BUGS.md, simulate.py all return 404 | CRITICAL | PROPOSED | [NINE-001](proposals/NINE-001-file-path-bugs.md) |
| NINE-002 | Memory search missing grok/twelve tables + delete allowlist stale | HIGH | PROPOSED | [NINE-002](proposals/NINE-002-memory-search-gaps.md) |
| NINE-003 | copilot_agent.py is a dead stub — remove or wire it | MEDIUM | PROPOSED | [NINE-003](proposals/NINE-003-copilot-agent-dead-stub.md) |
| NINE-004 | Duplicate agent DB entries + assign_ticket uses stale capitalised names | MEDIUM | PROPOSED | [NINE-004](proposals/NINE-004-db-duplicates-and-assign.md) |
| NINE-005 | memory_sonic / memory_scholar / memory_seeker DB tables missing | MEDIUM | PROPOSED | [NINE-005](proposals/NINE-005-missing-agent-db-tables.md) |
| NINE-006 | sandpits_new.py is a dead staging file — delete it | LOW | PROPOSED | [NINE-006](proposals/NINE-006-sandpits-new-dead-file.md) |

---

## Executed

*(None yet — this is the first Nine audit session)*

---

## Audit Summary — 2026-03-29

Full codebase audit performed by Nine as Ghost Layer System Architect.
Scope: all Python files, DB schema, documentation, sandpits, and API routes.

### What changed since my last session (2026-03-25/26)

| Area | Change |
|------|--------|
| File structure | Full reorganisation — 60+ Python files moved into agents/, core/, lib/, frontend/, utils/, tests/ |
| New agents | Grok (Agent 11), Twelve (Time Wizard Agent 12) — both active with sandpits and memory pools |
| New agents (planned) | Sonic, Scholar, Seeker — in roster but not yet wired |
| Two databases | swarm.db (appears unused/empty), swarm_memory.db (canonical, 40+ tables) |
| UI template | Now serving terminal_ui_v2.html via theme_engine.py (was terminal_base.html) |
| Decision system | Twelve introduced DECISION-XXX workflow, sandpits/twelve/ active |
| Time Wizard | New DB tables: decisions, time_events, time_journal, time_checkpoints, time_machine, daily_checkpoint |
| New endpoints | /api/nine, /api/nine/history, /api/nine/actions, /api/swarm/status, /api/time/timeline, /api/shell/execute, /api/monitor/stats, /api/tailscale |
| Theme engine | theme_engine.py + themes/fridays.json — CSS injection at render time |
| copilot_agent.py | Dead stub added — NOT the real Nine (see NINE-003) |

### What's working well
- Core pipeline (listener → orchestrator → debate → duck) compiles cleanly
- `/api/nine` endpoint correctly wired to claude_api.py
- Terminal UI serving via theme_engine with time-of-day themes
- All original agent memory pools intact (gemma:41, llama:42, nine:36, grok:41, eight:37)
- Time Wizard infrastructure complete (decisions table, API endpoints, Twelve sandpit)
- Approval token system (one-click trust/notify/ignore) present

### Remaining open issues (not yet proposed separately)
- `swarm.db` in root appears unused — verify and delete if confirmed empty
- `/api/nine/history` source filter too narrow — only shows 3 specific sources
- `memory_ten` empty (Agent Ten / Gemini dormant, never wired)
- 42 backend/console errors identified in AUDIT_V3 but not yet tracked through ALM
- Terminal shell view wiring confirmed working via `/api/shell/execute`
- Grok's `seven_fridays.py` REPL (`utils/seven_fridays.py`) — may need session review

---

## Numbering Convention

Nine uses `NINE-XXX` prefix to avoid collision with Twelve's `DECISION-XXX` sequence.
Both series live in their own agent sandpits.
Ghost approves all proposals from both.
