# 🎯 FRIDAYS REFINEMENT — LIVE TASK TRACKER

<!-- markdownlint-disable MD060 -->
<!-- markdownlint-disable -->

**Last Updated:** 2026-04-06 UTC  
**Session:** Session 8 — SVG Icon Overhaul + UI Density + Trace Fix + Test Repairs  
**Auditor:** Copilot (Ghost One direction)

Canonical ledgers for this tracker:
- Changes: `docs/changes/CHANGELOG_OPERATIONS.md`
- Audit evidence: `docs/audits/AUDIT_TRAIL.md`

## Session 8 Delta — UI Polish + Test Repairs

**Update Time:** 2026-04-06 UTC

| Item | Result | Notes |
|------|--------|-------|
| Scholar/Seeker removed from chat screen | ✅ DONE | `chat.js` |
| SVG icons applied throughout | ✅ DONE | `chat.js`, `chat.css`, `terminal_base.html` |
| Trace window: resize grip + compact size | ✅ DONE | `modals.css`, `toast.js`, `terminal_base.html` |
| Chat padding/border density cleanup | ✅ DONE | `chat.css` |
| Test suite stale imports fixed (3 files) | ✅ DONE | Post-modular-refactor paths |
| UAT gate: all 5 suites green | ✅ DONE | 21/21 e2e, 18/18 telegram, 6/6 alm |
| Root stale .md duplicates deleted | ✅ DONE | 3 files removed |

---

## Session 7 Delta — Identity Architecture + Cross-Reference Overhaul

**Update Time:** 2026-04-06 UTC

| Item | Result | Notes |
|------|--------|-------|
| System prompts rewritten (all 12) | ✅ DONE | `utils/config.py` — Ghost Layer → Developer/Worker/Ghost One tiers |
| THIRTEEN_SYSTEM_PROMPT written (was 1-line stub) | ✅ DONE | Full identity, SAP awareness, ALM rules, team roster |
| SAP awareness added to Nine/Twelve/Thirteen/Eleven | ✅ DONE | Now route SAP questions to Eight correctly |
| ALM gate bug fixed — confirmation loop | ✅ DONE | `chat.py` — `_derive_proposal_from_text()` suppressed for developer agents |
| ALM gate bug fixed — fs_write/fs_patch blocking | ✅ DONE | `chat.py` — `trust_level >= 1` gate bypassed for developer agents |
| Agent roster updated (`services.py`) | ✅ DONE | `developer_agent: True` flags; Ten→gpt-4o; Twelve→claude-haiku-4-5; Thirteen added |
| Permission model renamed + Thirteen added | ✅ DONE | `proposals.py`, `seed_agent_permissions.py` |
| DB seeder fixed (always-overwrite prompts) | ✅ DONE | `_schema.py` — prompts no longer locked to first-seed value |
| Missing agents added to seeder (Twelve/Thirteen/Scholar/Seeker) | ✅ DONE | `_schema.py` `_prompt_seed` |
| DB sync executed — agents tab shows current prompts | ✅ DONE | Inline Python sync script run |
| Agent module docstrings updated (all 7 developer agents) | ✅ DONE | "Ghost Layer" → "Developer Agent" |
| Orchestrator short prompts updated | ✅ DONE | `core/pipeline/orchestrator.py` |
| LINKED TO cross-reference headers added | ✅ DONE | All 5 core infra files + 7 agent modules |
| Cross-Reference Rule added to DEVELOPER_WORKFLOW.md | ✅ DONE | Mandatory for all change classes |
| ARCHITECTURE.md agent tiers updated | ✅ DONE | Nine/Ten/Eleven/Twelve/Thirteen/Scholar/Seeker documented correctly |
| CHANGELOG.md Session 7 entry written | ✅ DONE | Full change inventory |

## Next: Phase 5 — Cohesion

| Item | Status | Owner |
|------|--------|-------|
| `_build_context()` in `nine_agent.py` — remove "Mutating changes require approved proposals" for inline context | 🔲 OPEN | Nine/Ghost One |
| `_build_context()` in `twelve_agent.py` — same cleanup | 🔲 OPEN | Twelve/Ghost One |
| `thirteen_agent.py` — flesh out `_build_context()` stub | 🔲 OPEN | Thirteen/Ghost One |
| Verify relay: developer agents → Worker agents (e.g. Nine → Eight for SAP) | 🔲 OPEN | Nine |
| Duck + Sniffles awareness of Thirteen | 🔲 OPEN | Ghost One |

---

## Session 11 Delta - Comprehensive System Validation + Notification Reliability

**Update Time:** 2026-04-01 07:46 UTC

| Item | Result | Evidence |
|------|--------|----------|
| Baseline health (services + API + syntax) | ✅ DONE | `systemctl is-active` (4/4 active), `GET /` => 200, `python3 -m compileall -q frontend core lib fridays utils tests agents` |
| Core API + ALM suite | ✅ DONE | `python3 tests/test_e2e_fridays.py` => `21 PASS / 0 FAIL / 0 ERROR / 0 SKIP` |
| UAT gate (critical bundle) | ✅ DONE | `python3 tests/run_uat_gate.py` => PASS (compile + e2e + telegram_trust + manager_onboarding + alm_gate_endpoints) |
| Live chat/agent fanout | ✅ DONE | `python3 tests/test_chat_quality.py` => `16 PASS / 0 FAIL / 0 SKIP` (agent ping stage logs captured) |
| Channel command and trust smoke | ✅ DONE | `python3 tests/test_channel_smoke.py` => `7 PASS`; `python3 tests/test_direct_agent_commands.py` => `6 PASS`; `python3 tests/test_telegram_trust.py` => `18 PASS` |
| Terminal execution under ALM | ✅ DONE | `/api/hands/run` validated with executed proposal id + whitelisted command (`whoami`) |
| Notification SMTP delivery (both moderator addresses) | ✅ DONE | Diagnostic `send_reply()` to `jeandre.greyling@gmail.com` and `jeandre.greyling@outlook.com` both returned `True` |
| Notification reliability fix (code) | ✅ DONE | `core/pipeline/listener.py`, `fridays/telegram_bot.py`, `fridays/discord_bot.py` now treat `send_reply=False` as `notify_failed` and log explicitly |
| Self-healing Gmail Push recovery | ✅ DONE | `core/pipeline/listener.py` now retries push activation during IMAP fallback and switches back without restart when token/watch recover |
| Proposal notification heartbeat | ✅ DONE | `core/pipeline/listener.py` periodic task loop now includes `check_proposals()` in both push and IMAP modes |
| Terminal force-close recovery | ✅ DONE | `core/pipeline/ticket.py` now resolves Duck hook via package or legacy path; `/api/tickets/<id>/close` revalidated with synthetic ticket |
| Consolidated gate check | ✅ DONE | `python3 ops/daily_gate.py --quick` => FULLY OPERATIONAL |

### Session 11 Findings

| Finding ID | Severity | Finding | Status |
|------------|----------|---------|--------|
| OPS-NOTIFY-031 | HIGH | Unknown-sender notification paths could log success even when `send_reply` returned `False` (silent delivery miss) | ✅ FIXED |
| OPS-EMAIL-032 | MEDIUM | Gmail Push token had historical `invalid_grant` revocation events; listener falls back to IMAP polling | 🟡 PARTIAL (service works; push re-auth still required for instant push) |
| OPS-ALM-033 | LOW | `/api/hands/run` enforces ALM + whitelist (works as designed; non-whitelisted command rejected) | ✅ VERIFIED |
| OPS-TERM-034 | HIGH | Terminal dashboard force-close could fail with `No module named 'duck'` in some runtimes | ✅ FIXED |
| OPS-PROPOSAL-035 | MEDIUM | Proposal notifications were not part of the listener's regular periodic task sweep | ✅ FIXED |

### Operator Action Required (for instant push notifications)

1. Re-authorize Gmail push token to clear `invalid_grant` history and restore immediate push behavior.
2. Command path available in repo: `python3 lib/email/gmail_auth.py` (interactive OAuth flow).
3. After re-auth: restart listener (`sudo systemctl restart swarm-listener`) and confirm no new push errors in journal.

## Session 6 Delta - Channel Stabilization + Vortex Evidence

**Update Time:** 2026-03-30 13:30 UTC

| Item | Result | Evidence |
|------|--------|----------|
| Telegram/Discord queue recovery hardening | ✅ DONE | `fridays/telegram_bot.py`, `fridays/discord_bot.py`, `core/pipeline/queue_manager.py` |
| Pipeline failure event logging | ✅ DONE | `pipeline_failed` activity path added for both channel front doors |
| Vortex dry-run drift correctness | ✅ DONE | `core/time_machine.py` now reports `added_since_checkpoint` drift |
| Cross-channel reliability backlog registration | ✅ DONE | `docs/BUGS.md` BUG-028/BUG-029 |
| Full cross-channel UAT execution | 🟡 NEXT | New UAT section below; run and capture evidence in test log |

## Session 10 Delta - Fridays End-to-End ALM Validation

**Update Time:** 2026-03-31 06:25 UTC

| Item | Result | Evidence |
|------|--------|----------|
| Full syntax sweep across active code paths | ✅ DONE | `python3 -m compileall -q frontend core lib fridays utils tests agents` |
| Chat/monitor regression suite | ✅ DONE | `python3 tests/test_chat_quality.py` => `14 PASS / 0 FAIL / 0 SKIP` |
| Multi-agent pending lifecycle validation | ✅ DONE | `/api/chat` fanout + `/api/chat/jobs/status` completion checks |
| Email transport validation (both mailboxes) | ✅ DONE | IMAP + SMTP auth OK for `sevenpotato9` and `ninepotato7` |
| Email round-trip through project handler | ✅ DONE | `email_handler.send_reply()` + IMAP token search hit |
| ALM lifecycle smoke proposal | ✅ DONE | `INTERNAL-NINE-0216` moved `pending -> approved -> executed` |
| Bug triage + remediation | ✅ DONE | `INTERNAL-TEN-0217` executed: Flask dev server warning removed (threaded WSGI runtime) |

### Session 10 Bugs Logged and Triaged

| Proposal ID | Issue | Status | Notes |
|-------------|-------|--------|-------|
| `INTERNAL-TEN-0217` | `swarm-terminal` ran with Flask development server warning | ✅ EXECUTED | Migrated runtime bootstrap in `frontend/terminal.py` to threaded stdlib WSGI server with IPv6/IPv4 fallback |

### Backlog Added From Session 6

| Backlog ID | Priority | Item | Owner | Status |
|------------|----------|------|-------|--------|
| OPS-CH-001 | HIGH | Run governed E2E cycle for Email + Telegram + Discord, with queue/ticket closure assertions | Ten (GPT)/Twelve | OPEN |
| OPS-CH-002 | HIGH | Validate channel response consistency under error injection (ensure queue reset + retry path) | Ten (GPT) | OPEN |
| OPS-VTX-001 | MEDIUM | Validate Vortex slider preview in primary 5050 service after restart with updated restore logic | Ten (GPT) | OPEN |

---

## 📋 Master Todo List

| # | Task | Status | Owner | Notes |
|---|------|--------|-------|-------|
| 1 | Comprehensive Fridays tile audit | ✅ COMPLETE | Twelve | Found 8 tiles, 45+ endpoints; 1 broken pipe (docs) fixed |
| 2 | Document all findings in BUGS_AUDIT.md | ✅ COMPLETE | Twelve | FRIDAYS_AUDIT_SUMMARY.md and BUGS_AUDIT created |
| 3 | **Fix broken pipes systematically** | ✅ COMPLETE | Twelve | Docs tile fixed (BRK-001); Chat timeout identified (BRK-002); Agent tasks created |
| 4 | Test each tile after fixes | ✅ EXECUTED | Twelve | 18/19 E2E tests PASS; results in ALM_TEST_SPECIFICATION.md |
| 5 | Update CHANGELOG with all changes | ✅ COMPLETE | Ten (GPT) | All fixes + world clocks documented in CHANGELOG.md |
| 6 | Fix critical user-facing bugs | ✅ COMPLETE | Ten (GPT) | BUG-1 through BUG-5 fixed; Telegram listener restored |

---

## 🔧 BROKEN PIPES STATUS UPDATE

## ✅ Proactive Ops Run (Dry Test + Approvals/Proposals Audit)

**Run time:** 2026-03-30 00:55-01:05 UTC

| Item | Result | Evidence |
|------|--------|----------|
| Dry triage script | ✅ PASS (24/24) | `SIMULATE=true python3 tests/test_triage_queue_dryrun.py` |
| Full tests via pytest | ⚠️ BLOCKED | `python3 -m pytest` failed (`No module named pytest`) |
| Full pipeline simulate | ⚠️ PARTIAL | `utils/simulate.py` entered live model path; Gemma route call exceeded 174s |
| Proposal queue DB | ✅ AUDITED | `work_proposals`: 5 total (4 executed, 1 pending) |
| Decisions audit table | ✅ AUDITED | `decisions`: 18 total records |
| Time Wizard tables | ✅ AUDITED | `time_journal`: 1, `time_events`: 4, `time_checkpoints`: 2 |

### Backlog Added From This Run

| Backlog ID | Priority | Item | Owner | Status |
|------------|----------|------|-------|--------|
| OPS-DRY-001 | HIGH | Add pinned test environment with pytest installed for `python3 -m pytest tests -q` | Ten (GPT) | OPEN |
| OPS-DRY-002 | HIGH | Add model-stub mode to `utils/simulate.py` so full dry simulation finishes without live model latency | Ten (GPT) | OPEN |
| OPS-APR-001 | MEDIUM | Reconcile proposal file status vs DB status for `NINE-021` (file says executed, DB still pending) | Nine/Ten (GPT) | ✅ CLOSED |

### Self-Audit Delta (10:18 UTC)

| Check | Result | Notes |
|------|--------|-------|
| API connection sweep | ✅ 11/11 pass | Includes restored `/api/queue` + `/api/work-proposals` |
| Chat smoke test | ✅ pass | `/api/chat` returned ok+response |
| Proposal backlog | ✅ cleared | `work_proposals` now `executed=6`, `pending=0` |
| Code diagnostics (frontend/core/fridays/utils/tests) | ✅ clean | `get_errors` returned no issues |

### ALM Governance Delta (10:30 UTC)

| Control | Status | Evidence |
|--------|--------|----------|
| Documentation-first ALM driver | ✅ active | `docs/ALM_DRIVER.md` |
| Queue/approval cookbook | ✅ active | `docs/ALM_COOKBOOK.md` |
| Proposal gate on mutating APIs | ✅ active | `frontend/terminal.py` (`/api/shell/execute`, `/api/skills/run`, `/api/exec`, `/api/exec/write`) |
| Sniffles re-enabled verification | ✅ confirmed | `/api/agents` shows `sniffles.enabled = true` |
| Fridays ALM visibility | ✅ active | Home ALM stat + Studio governance line + Monitor governance block via `/api/alm/status` |
| Theme-layer ALM bake-in | ✅ active | `theme_engine` now injects `window._almData` + `initALMData()` into all themed renders |
| ALM lifecycle logging for this change | ✅ complete | `INTERNAL-COPILOT-0102` created → approved → executed |

### Priority 1 — Blocking UI Functionality

| Pipe | Status | Impact | Root Cause | Fix | Updated |
|------|--------|--------|-----------|-----|---------|
| **Docs Tile Empty** | ✅ FIXED | Was: Docs tab showed "No docs" | Fixed: _DOCS_DIR path was wrong (`frontend/swarm_docs` instead of `docs`) | ✅ Changed path to `../docs`; generated 9 HTML docs; endpoint now returns files | ✅ |
| **Chat POST Timeout** | ✅ FIXED | Sending chat messages hangs indefinitely | Implemented 10-second timeout with ThreadPoolExecutor fallback | ✅ Returns graceful fallback message instead of hanging | 2026-03-30 |
| **Terminal Tile (Empty)** | 🟡 HIGH | Terminal tile displays but has no shell output | `/api/hands/run` endpoint exists but may not be called; need to verify JS executeCommand() function | Verify endpoint calls + test with simple commands | ✅ |
| **Ticket Click Handler** | ✅ FIXED | BUG-1: Tickets not clickable in home queue | onclick handler broken | ✅ Now calls `openTicketDetail()` directly | 2026-03-29 15:20 |
| **Memory Modal** | ✅ FIXED | BUG-2: Memory expand not working | expandMemory() function missing | ✅ Added proper modal with API integration | 2026-03-29 15:20 |
| **Docs Modal** | ✅ FIXED | BUG-3: Docs click not opening | openDocDetail() function missing | ✅ Opens `/docs/html/<filename>` with KB fallback | 2026-03-29 15:20 |
| **Studio Proposals** | ✅ FIXED | BUG-4: Proposals not visible | loadProposals() not called | ✅ Wired to `/api/proposals/approve` and `/api/proposals/reject` | 2026-03-29 15:20 |
| **Telegram Queue Crash** | ✅ FIXED | BUG-5: CRITICAL — All Telegram messages crashed on DB INSERT | 8 values for 7 columns in `ticket.create()` | ✅ Removed redundant `get_timestamp()` parameter | 2026-03-29 15:20 |

### Priority 2 — Data Flow Issues

| Pipe | Status | Impact | Root Cause | Fix |
|------|--------|--------|-----------|-----|
| **Nine File Operations** | ✅ VERIFIED | Prior signature mismatch fixed; tuple return contract validated | BUG-019 resolved and regression-tested in dry-run cycle | Move to monitor-only unless regression appears |
| **Email Handler** | 🟢 MEDIUM | mailto: approval links untested | BUG-001 marked `needs_verification` | Run UAT scenario |

---

## ✅ VERIFIED & NEW FEATURES

### Dashboard Features (Session 5)
| Feature | Status | Details |
|---------|--------|---------|
| **World Clocks** | ✅ LIVE | 5 timezones (Melbourne, Singapore, Delhi, Cape Town, NYC) with 1s real-time update |
| **Layer Switcher** | ✅ LIVE | Toggle between Fridays UI and Console Layer |
| **Ticket Modal** | ✅ LIVE | Click ticket → full detail view with notes + actions |
| **Memory Expansion** | ✅ LIVE | Click memory item → detail modal from agent memory API |
| **Doc Viewer** | ✅ LIVE | Click doc → modal with `/docs/html/<filename>` content |
| **Proposal Management** | ✅ LIVE | Studio tile shows all proposals with Approve/Reject buttons |

### Verified Working Tiles
| Tile | Endpoint | Response | Status |
|------|----------|----------|--------|
| 💬 Chat | `/api/conversations` | ✅ 40 conversations | Working |
| 🎯 Memory | `/api/agents/memories/query` | ✅ Full search working | Working |
| 📊 Monitor | `/api/monitor` | ✅ System stats | Working |
| 🎟️ Tickets | `/api/tickets` | ✅ 65 tickets | Now clickable + detail modal |
| 🛠️ Skills | `/api/skills` | ✅ 11 skills | Working |
| 👥 Agents | `/api/agents` | ✅ 15 agents | Working |
| 📁 Sandpits | `/api/sandpits` | ✅ Agent workspaces | Working |
| 🕐 World Clocks | New | ✅ 5 timezone display | NEW |

---

## 🚀 NEXT STEPS (IN ORDER)

### Phase 1 — Remaining High-Priority Fixes

**BRK-002: Chat POST Timeout** ✅ FIXED
- ✅ Implemented 10-second timeout wrapper with ThreadPoolExecutor
- ✅ Return helpful fallback message on timeout instead of hanging
- ✅ Chat feature now responsive and returns within 10 seconds
- ✅ Commit: `cabd023`

### Phase 2 — Integration Testing

**BRK-003: Terminal Tile Command Execution**
- [ ] Verify `executeCommand()` JS function is called
- [ ] Check `/api/hands/run` or `/api/shell/execute` endpoint
- [ ] Test with simple command: `whoami`

**TIME WIZARD INITIALIZATION** ✅ FIXED
- ✅ Added bootstrap_session() method for system startup
- ✅ Integrated into scheduler.py main_loop()
- ✅ Sessions now created automatically on system start
- ✅ Decision execution events logged
- ✅ Temporal statistics fully functional
- ✅ API endpoints: /api/time/bootstrap, /api/time/log-decision, /api/time/decision-history
- ✅ Commit: `60c0999`

**BRK-004: Nine File Operations**
- [x] Test `fridays.file_agent.read_sandpit()` 
- [x] Test `fridays.file_agent.write_sandpit()`
- [x] Verify return types are `(ok, content)` tuples

**BRK-005: End-to-End Flows**
- [ ] Email → Ticket → Agent Response → Reply (full round-trip)
- [ ] Discord message → Ticket creation → Response
- [ ] Telegram command → Sandpit file write

---

## 📊 Session 5 Summary (Final Update)

**What was completed:**
✅ 5 critical user-facing bugs fixed  
✅ World clocks implemented + live  
✅ Layer switcher working  
✅ Ticket detail modal operational  
✅ Memory + docs modal integration  
✅ Studio proposals functional  
✅ Telegram listener restored  
✅ **Chat endpoint timeout FIXED (BRK-002)** 🔴→✅  
✅ **Time Wizard initialization + session tracking FIXED** ⏳✅
✅ Comprehensive audit + documentation  

**Files modified:** 17 (timeline.py, terminal.py, time_machine.py, scheduler.py, etc.)  
**Commits:** 23 (includes BRK-002 + Time Wizard fixes)  
**Bootstrap tests:** 7/7 pass  

**What remains:**
🟡 Terminal tile verification  
🟢 Nine file operations validation (completed in prior bugfix cycle)  
🟡 End-to-end email/Discord/Telegram flow testing
🟡 Deterministic full dry simulation (currently blocked by live model latency)

## 📊 AUDIT METRICS

**Endpoint Health:** 8/8 tiles responding (100%)  
**Data Quality:** 7/8 tiles returning data (87.5%)  
**Broken Pipes:** 3 critical, 2 high priority  
**Estimated Fix Time:** 4-6 hours total  

---

## 🔐 DOCUMENTATION STANDARD

**Each broken pipe fix must:**
1. ✅ Have test endpoint call before/after
2. ✅ Update this tracker with status
3. ✅ Add entry to CHANGELOG.md
4. ✅ Include rollback plan if needed

---

## 🎯 SUCCESS CRITERIA FOR REFINEMENT PHASE

- ✅ All 8 tiles load data correctly
- ✅ All write operations (chat, proposals, sandpit) succeed
- ✅ End-to-end flows verified (email→response, Discord, Telegram)
- ✅ All tests pass (0 timeouts)
- ✅ Documentation updated (CHANGELOG, this tracker)
- ✅ System ready for Nine's integration audit
