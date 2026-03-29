# Nine — Decision Index

**Agent**: Nine (System Architect · Ghost Layer)
**Last Updated**: 2026-03-29 (session 4 — Time Wizard fix + Fridays proposal queue)
**Numbering**: NINE-XXX (separate from Twelve's DECISION-XXX)

---

## Active Proposals

None — all proposals executed.

## Executed This Session (Session 4)

| ID       | Title                                                      | Priority | Status   |
| -------- | ---------------------------------------------------------- | -------- | -------- |
| NINE-019 | Time Wizard fix + Fridays internal proposal queue          | HIGH     | EXECUTED |
| NINE-020 | change_logger.py + git post-commit hook (Time Wizard live) | HIGH     | EXECUTED |

## Executed This Session (Session 3)

| ID       | Title                                                   | Priority | Status   |
| -------- | ------------------------------------------------------- | -------- | -------- |
| NINE-018 | Fix triage queue bugs — 5 bugs, email + Telegram queues | CRITICAL | EXECUTED |

## Executed This Session (Session 2)

| ID       | Title                                        | Priority | Status   |
| -------- | -------------------------------------------- | -------- | -------- |
| NINE-008 | orchestrator.py _re NameError fix            | HIGH     | EXECUTED |
| NINE-009 | agent_proposals.py sniff_sandpit alias fix   | MEDIUM   | EXECUTED |
| NINE-010 | fridays/scheduler.py missing functions       | HIGH     | EXECUTED |
| NINE-011 | expandTwDecision 404 glob double-prefix fix  | HIGH     | EXECUTED |
| NINE-012 | /api/decisions/{id} flat field extraction    | MEDIUM   | EXECUTED |
| NINE-013 | Ticket search #ticket-search wired           | LOW      | EXECUTED |
| NINE-014 | ARCHITECTURE.md agents 8-12 added + DB table | MEDIUM   | EXECUTED |
| NINE-015 | FILE_STRUCTURE.md swarm.db ref removed       | LOW      | EXECUTED |
| NINE-016 | NINE-001..006 proposals marked EXECUTED      | LOW      | EXECUTED |
| NINE-017 | DECISION-003 marked EXECUTED + test log done | MEDIUM   | EXECUTED |

---

## Executed

| ID       | Title                                               | Executed   | Session   |
| -------- | --------------------------------------------------- | ---------- | --------- |
| NINE-001 | File path bugs — 4 broken dashboard endpoints       | 2026-03-29 | session 1 |
| NINE-002 | Memory search gaps — grok/twelve missing            | 2026-03-29 | session 1 |
| NINE-003 | copilot_agent.py dead stub — deleted                | 2026-03-29 | session 1 |
| NINE-004 | DB duplicates + assign_ticket stale names           | 2026-03-29 | session 1 |
| NINE-005 | memory_sonic/scholar/seeker tables created          | 2026-03-29 | session 1 |
| NINE-006 | sandpits_new.py dead file — deleted                 | 2026-03-29 | session 1 |
| NINE-007 | Ghost Brief intelligence feed — built and live      | 2026-03-29 | session 1 |
| NINE-008 | orchestrator.py _re NameError — fixed               | 2026-03-29 | session 2 |
| NINE-009 | agent_proposals.py sniff_sandpit alias fixed        | 2026-03-29 | session 2 |
| NINE-010 | fridays/scheduler.py 3 missing functions added      | 2026-03-29 | session 2 |
| NINE-011 | expandTwDecision 404 glob double-prefix fixed       | 2026-03-29 | session 2 |
| NINE-012 | /api/decisions/{id} flat field extraction added     | 2026-03-29 | session 2 |
| NINE-013 | ticket-search input wired in Tickets window         | 2026-03-29 | session 2 |
| NINE-014 | ARCHITECTURE.md expanded: agents 8-12, 40+ tables  | 2026-03-29 | session 2 |
| NINE-015 | FILE_STRUCTURE.md swarm.db ref removed              | 2026-03-29 | session 2 |
| NINE-016 | NINE-001..006 proposals marked EXECUTED             | 2026-03-29 | session 2 |
| NINE-017 | DECISION-003 marked EXECUTED, test log completed    | 2026-03-29 | session 2 |
| NINE-018 | Fix triage queue — 5 bugs in listener/duck/ticket   | 2026-03-29 | session 3 |
| NINE-019 | Time Wizard fix + Fridays internal proposal queue   | 2026-03-29 | session 4 |

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

### Remaining open issues (session 1 — now resolved)

- `swarm.db` — DELETED (confirmed empty, NINE-006 adjacent)
- `copilot_agent.py` — DELETED (NINE-003)
- `sandpits_new.py` — DELETED (NINE-006)
- Memory search gaps — FIXED (NINE-002)
- DB duplicates — FIXED (NINE-004)

### Remaining open issues (session 2 — carry forward)

- Studio sub-sections (queue/logs/config) are stubs — "coming soon" text only
- `openTicketDetail()` is a stub — console.log only, no detail view
- `showAgentDetails()` is a stub — console.log only
- `/api/nine/history` source filter too narrow
- `memory_ten` empty (Agent Ten / Gemini dormant, never wired)
- 42 backend/console errors from AUDIT_V3 not yet tracked through ALM

### Session 2 — What was fixed

- 3 Python runtime bugs: `_re` NameError, `sniff_sandpit` alias, 3 missing scheduler functions
- 3 UI bugs: expandTwDecision 404, decision detail flat fields, ticket-search wiring
- All proposal files (NINE-001..006) status corrected to EXECUTED
- DECISION-003 marked EXECUTED, test log completed
- ARCHITECTURE.md: agents 8-12 documented, DB table count corrected (40+ tables)
- FILE_STRUCTURE.md: removed deleted swarm.db reference
- All 4 services confirmed active throughout session

---

## Numbering Convention

Nine uses `NINE-XXX` prefix to avoid collision with Twelve's `DECISION-XXX` sequence.
Both series live in their own agent sandpits.
Ghost approves all proposals from both.
