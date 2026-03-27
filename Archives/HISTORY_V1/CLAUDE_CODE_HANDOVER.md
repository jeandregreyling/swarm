# Claude Code Handover Brief
## Seven's Swarm — Session 9 Handover
## Status: Foundation UAT passed. simulate.py 4/4. Phase 3 ready.

---

## Read first
1. VS_CODE_CONTEXT.md — current state, what works, services, rules
2. PROJECT.md — full architecture, vision, phase plan
3. config.py — system prompts (read-only, never share, never modify casually)

---

## Current state — what works and is UAT verified

Everything in Sessions 1–8 is built. Session 9 found and fixed all foundation bugs,
then ran a live end-to-end UAT via the real listener service. All passed.
simulate.py then ran 4/4 with 12 simulated emails intercepted.

**Full email pipeline (Ghost → Swarm → Ghost):**
- Gemma reads receipt (Email 0) before any model loads
- LLaMA fast response (Email 1) with web search or system health data
- Qwen + Gemma full verdict (Email 2), debate section if fired
- Duck sanity check on every close
- Duck queue-clear email when queue hits zero

**FL-001 routing — all flags wired:**
- NEEDS_WEB: controls web search
- AGENTS: llama / qwen / both (normalised — Gemma may return 'llama/qwen', handled)
- MODE: consult / debate
- IS_IDENTITY: skips web, agents answer from context
- IS_SAP: Eight three-voice pipeline
- IS_SYSTEM: live health data injected from monitor.py

**Sender classification:**
- trusted → full pipeline
- moderator → command handler, falls through to pipeline if no command
- notification → silent filing
- unknown → pending queue + one-click approval links to Ghost

**Terminal (port 5050):**
- Chat with live SSE streaming
- Kill switches per agent
- Memory browser, tickets, agents, system, sandpits views
- /approve/<action>/<token> endpoint for one-click email approval

---

## Session 9 — all fixes (complete)

### Bug fixes

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | database.py | add_notification_sender used label/note columns — don't exist in live DB | Fixed column names to notes, removed label |
| 2 | database.py | save_gemma_verdict missing source='verdict' in INSERT into memory_gemma | Added source column |
| 3 | monitor.py | record_stats() calculated cpu_temp but never inserted it | Added to INSERT |
| 4 | monitor.py | get_current_stats() used wrong positional row indices (DB column order changed) | Fixed to named access |
| 5 | orchestrator.py | gemma_route() agents 'llama/qwen' not normalised — LLaMA silenced in stage1 | Normalised to 'both' |
| 6 | orchestrator.py | Same root cause — Qwen silenced in stage2 when agents='llama/qwen' | Same fix, shared routing dict |
| 7 | duck.py | _log_to_duck_log INSERT missing ticket_id column | Resolves ticket_id from tickets table before INSERT |
| 8 | claude_api.py | _log_call INSERT missing ticket_id column | Resolves ticket_id from tickets table before INSERT |

### Wiring fixes

| # | What was missing | Fix |
|---|-----------------|-----|
| 1 | on_queue_clear() defined but never called | Wired into listener.py after librarian_close when queue=0 |
| 2 | mark_processing() defined but never called | Wired into listener.py and terminal.py before stage1 |
| 3 | Ghost couldn't ask questions by email | Moderator path now falls through to pipeline when no command found |

### Schema fixes (8 tables)
All SCHEMA definitions in database.py corrected to match live DB:
trusted_senders, notification_senders, pending_emails, moderators, agents,
duck_log, sniffer_log, system_stats

### Dead code removed
- database.py: create_ticket() was unreachable — removed. ticket.create() owns ticket creation.

### Data completeness
- housekeeping.py: archive_old_memories() and deduplicate_memories() now include memory_eight
- eight.py: removed stale `build_shared_context` import from database (only in __main__ test block)
- ticket.py: create() INSERT now includes queue_id column (was passing it but not saving it)

---

## Two pending actions — require Ghost's password

**1. Install terminal service (do this now):**
```bash
sudo cp /home/seven/swarm/swarm-terminal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable swarm-terminal.service
sudo systemctl start swarm-terminal
```
Without this, terminal only runs manually and dies on reboot. Approval links depend on it.

**2. Enable Ghost Circle (do when ready for Phase 3):**
```bash
sudo nano /etc/environment   # add: ANTHROPIC_API_KEY=sk-ant-...
source /etc/environment
python3 /home/seven/swarm/claude_api.py   # should print: ✓ Ghost Circle connected
sudo systemctl restart swarm-listener
```

---

## Known issues — none

No known bugs. All modules import clean. simulate.py 4/4. Live UAT passed.
UAT test scripts at UAT_TEST_SCRIPTS.md — 29 tests for Ghost sign-off.

---

## Phase 3 — what to build next

Complete Ghost's UAT sign-off (UAT_TEST_SCRIPTS.md) first.
Then pick any Phase 3 item:
- RL-018: File + browser agent (Playwright)
- RL-019: Shell agent (sandboxed whitelist)
- RL-020: Scheduler (proactive tasks)
- RL-021: Skills framework
- RL-022: Telegram bot
- RL-023: Discord bot
- RL-024: WhatsApp
- RL-011: Gmail Push Notifications (replace 60s poll)

---

## Rules that must not break

- Never touch nvme0n1p1 (EFI)
- OLLAMA_HOST=0.0.0.0 stays in ollama service override
- Librarian only receives content to tag — never full pipeline context
- Duck runs after EVERY ticket close
- Sniffles never interrupts active queue
- Gemma routes every question before anything fires
- Before closing an RL item: verify call sites wired, service file exists, simulate.py passes

