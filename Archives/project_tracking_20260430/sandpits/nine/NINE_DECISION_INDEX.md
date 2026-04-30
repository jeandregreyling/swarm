# Nine — Decision Index

**Agent**: Nine (System Architect · Ghost Layer)
**Last Updated**: 2026-03-31 (session 5 stress test — CRITICAL email pipeline fix, 10 bugs fixed total)
**Numbering**: NINE-XXX (separate from Twelve's DECISION-XXX)

---

## Active Proposals

None — all proposals executed.

## Executed This Session (Session 5 Stress Test — 2026-03-31)

| ID       | Title                                                                          | Priority | Status   |
| -------- | ------------------------------------------------------------------------------ | -------- | -------- |
| NINE-023 | Session 5 stress test — CRITICAL email pipeline fix + gmail_push path fix      | CRITICAL | EXECUTED |

### NINE-023 Bug Details

- **NINE-023-A (CRITICAL)** `core/pipeline/listener.py` — `get_timestamp` never imported. All trusted email pipeline runs crashed at read receipt. ZERO emails sent since this was introduced. Fixed: added `get_timestamp` to `from system_clock import ...`.
- **NINE-023-B** `lib/email/gmail_push.py` — `TOKEN_FILE` and `WATCH_STATE_FILE` pointed to swarm root but actual files in `lib/email/`. `listener.py` `push_token` check also wrong path. Listener always ran in IMAP poll mode (60s delay). Fixed both. Listener now runs Gmail Push (instant).
- **NINE-023-C** `swarm-monitor.service` — ExecStart points to `/home/seven/swarm/monitor.py` (missing). File at `lib/system/monitor.py`. REQUIRES GHOST SUDO to fix service unit.
- **NINE-023-D** `swarm-terminal` service inactive/dead — orphan process from browser session holds port 5050. Informational — not code fix. REQUIRES GHOST to kill orphan and restart service.
- **NINE-023-E** Queue entries 220/221 stuck `queued` — abandoned (pipeline crashed before completion, no replay possible without re-receiving email).

---

## Executed This Session (Session 5 Pass 2 — 2026-03-31)

| ID         | Title                                                                              | Priority | Status   |
| ---------- | ---------------------------------------------------------------------------------- | -------- | -------- |
| NINE-022p2 | Session 5 Pass 2 audit - 4 more bugs fixed (DB schema drift, /api/health, ddgs)    | HIGH     | EXECUTED |

### NINE-022 Pass 2 Bug Details

- **BUG-E** `utils/database.py` SCHEMA — `time_events`, `time_journal`, `time_checkpoints` had OLD column definitions (description/metadata/entry/name/state_snapshot) that don't match live DB columns (action/target/state_hash/details/session_id/phase/status/notes/checkpoint_name/full_state). Fixed in SCHEMA and `_migrate_schema` fallback loop.
- **BUG-F** `utils/database.py` `_migrate_schema()` — `approval_tokens` fallback DDL had stale schema `(pending_email_id, used)` instead of production schema `(target_email, created_by, used_at, status)`. `use_approval_token()` queries `status` column — fallback path would fail. Fixed to match SCHEMA and live DB.
- **BUG-G** `frontend/terminal.py` — `/api/health` route missing. Health checks returned 404. Added `GET /api/health` endpoint.
- **BUG-H** `lib/search/internet.py` — Hard `from ddgs import DDGS` with no import guard. Crashes in environments without `ddgs` in PYTHONPATH. Added try/except with `duckduckgo_search` fallback and graceful degradation.

## Executed This Session (Session 5 Pass 1 — 2026-03-31)

| ID       | Title                                                                      | Priority | Status   |
| -------- | -------------------------------------------------------------------------- | -------- | -------- |
| NINE-022 | Session 5 full system audit — 4 bugs fixed (change_logger, DB schema, CSS) | HIGH     | EXECUTED |

### NINE-022 Pass 1 Bug Details

- **BUG-A** `utils/change_logger.py` `mark_executed()` — broken subquery marked ALL pending `work_proposals` as executed on any decision PASS. Fixed to scope by `proposal_file` match.
- **BUG-B** `utils/database.py` SCHEMA — `daily_checkpoint` defined with wrong columns; would break fresh installs causing `twelve_agent.py` query failures. SCHEMA updated to match live DB.
- **BUG-C** `utils/database.py` SCHEMA + `_migrate_schema()` — `ghost_briefs` and `scheduled_tasks` tables used in production code but absent from SCHEMA and migrate block. Added to both.
- **BUG-D** `frontend/templates/terminal_base.html` — CSS vars `--danger`, `--shadow`, `--glass-blur`, `--glass-opacity` used by floating window styles but undefined in fallback `:root` block. Fallback values added.

---

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
| NINE-020 | change_logger.py + git post-commit hook live        | 2026-03-29 | session 4 |
| NINE-022 | Session 5 audit — 4 bugs fixed across 3 files       | 2026-03-31 | session 5 |

---

## Audit Summary — 2026-03-29

Full codebase audit performed by Nine as Ghost Layer System Architect.
Scope: all Python files, DB schema, documentation, sandpits, and API routes.

### What changed since my last session (2026-03-25/26)

| Area | Change |
| ---- | ------ |
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
