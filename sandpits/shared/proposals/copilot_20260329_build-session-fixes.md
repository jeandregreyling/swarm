# PROPOSAL
## Agent: copilot
## Date: 2026-03-29
## Summary: Swarm build session — UI fixes, pipeline repairs, ALM foundations

---

## What Was Done This Session

This proposal documents the architectural and UI changes made during the 29 March 2026 build session, submitted for Seven's review and KB archival.

### Pipeline Fixes
- **ask_agent() case-sensitivity**: Normalized `agent_name = agent_name.lower()` in `orchestrator.py`. All calls using `'Gemma'` (capital-G) now resolve correctly to the `AGENTS` dict key `'gemma'`. This was causing every Telegram pipeline message to fail with `Pipeline error: 'Gemma'`.
- **log_activity() signature**: Updated `database.py` `log_activity()` to accept optional 4th `severity` arg. `logging_bridge.log_action()` was passing 4 args; database function only accepted 3. Fixed without breaking existing callers.
- **ticket.create() INSERT**: Removed spurious `get_timestamp()` 8th value from INSERT with 7 columns. Was causing `8 values for 7 columns` error on every Telegram ticket creation.

### UI Improvements
- **Home screen ticket click**: Changed onclick to call `openTicketDetail()` directly (was opening Tickets window requiring second click)
- **Memory click**: Implemented real detail modal with full content fetch
- **Docs click**: Implemented `openDocDetail()` modal fetching doc content
- **Studio proposals**: Replaced static grid with live proposals list wired to approve/reject API
- **Layer switcher**: Added toggle button on both terminal layers (`/` and `/v2`)
- **Ticket detail modal**: Full implementation with notes, status badges, duck result, final answer

### Proposed Next Steps
1. Ticket editing: tags chips + add-note textarea + PATCH route
2. Agent Network panel in Studio (Nine, Ten, Eleven with status)
3. ALM convention documented in KB

---

## Files Changed
- `core/pipeline/orchestrator.py` — ask_agent() normalization
- `utils/database.py` — log_activity() signature fix
- `core/pipeline/ticket.py` — INSERT fix
- `frontend/templates/terminal_base.html` — all UI improvements
- `frontend/terminal.py` — /v2 route, proposals API
- `frontend/theme_engine.py` — template param
- `fridays/telegram_bot.py` — no changes (fixed via orchestrator)

## Risk Assessment
- Low risk: all fixes are targeted and isolated
- Pipeline fix restores Telegram to full function
- UI fixes are frontend-only (no data model changes)
