# 🎯 FRIDAYS REFINEMENT — LIVE TASK TRACKER

**Last Updated:** 2026-03-28 22:55 UTC  
**Session:** Refinement Phase — Six Todos / Audit Mode  
**Auditor:** Agent Twelve (Ghost Layer Architect)  

---

## 📋 Master Todo List

| # | Task | Status | Owner | Notes |
|---|------|--------|-------|-------|
| 1 | Comprehensive Fridays tile audit | ✅ COMPLETE | Twelve | Found 8 tiles, 45+ endpoints; 1 broken pipe (docs) |
| 2 | Document all findings in BUGS_AUDIT.md | ✅ COMPLETE | Twelve | FRIDAYS_AUDIT_SUMMARY.md and BUGS_AUDIT_28_March_2026.md created |
| 3 | **Fix broken pipes systematically** | 🔄 IN PROGRESS | Twelve | Identified issues below; starting fixes |
| 4 | Test each tile after fixes | ⏳ QUEUED | Twelve | Depends on #3 |
| 5 | Update CHANGELOG with all changes | ⏳ QUEUED | Twelve | Auto-generated after fixes complete |
| 6 | Verify Nine integration readiness | ⏳ QUEUED | Nine/Twelve | Pending file operations validation |

---

## 🔧 BROKEN PIPES IDENTIFIED

### Priority 1 — Blocking UI Functionality

| Pipe | Status | Impact | Root Cause | Fix |
|------|--------|--------|-----------|-----|
| **Docs Tile Empty** | 🔴 CRITICAL | Docs tab shows "No docs" despite files existing | `/docs/html/` directory doesn't exist; API returns `[]` | Create `/docs/html/` directory + convert `.md` files to `.html` |
| **Chat POST Timeout** | 🔴 CRITICAL | Sending chat messages hangs indefinitely | `/api/chat` calls orchestrator; orchestrator waits for Ollama models | Need to verify Ollama is running or add timeout/fallback |
| **Terminal Tile (Empty)** | 🟡 HIGH | Terminal tile displays but has no functionality | No `/api/terminal/run` or equivalent wired | Verify `executeCommand()` JS function calls correct endpoint |

### Priority 2 — Data Flow Issues

| Pipe | Status | Impact | Root Cause | Fix |
|------|--------|--------|-----------|-----|
| **Nine File Operations** | 🟡 HIGH | Nine cannot read/write sandpits | fridays/file_agent.py signature mismatch (BUG-019 partially fixed) | Complete Nine file operation testing |
| **Proposals Tile** | 🟡 HIGH | Proposal system untested end-to-end | Load function `loadProposals()` exists but not verified | Test proposal write/read/list flow |
| **Discord/Telegram** | 🟡 HIGH | Integration untested end-to-end | Services restart but message flow not validated | Test each service bot flow end-to-end |

### Priority 3 — Infrastructure

| Pipe | Status | Impact | Root Cause | Fix |
|------|--------|--------|-----------|-----|
| **Ollama Model Status** | 🟢 MEDIUM | Chat timeout suggests models not available | Models may not be running; no health check | Add `/api/health` endpoint to verify model availability |
| **Email Handler** | 🟢 MEDIUM | mailto: approval links untested | BUG-001 marked `needs_verification` |  Run UAT scenario: send email → click approval link → verify processing |

---

## ✅ VERIFIED WORKING TILES

| Tile | Endpoint | Response | Data Quality |
|------|----------|----------|--------------|
| 💬 Chat | `/api/conversations` | ✅ 40 conversations | Title, source, timestamp present |
| 🎯 Memory | `/api/agents/memories/query` | ✅ Full search working | Query results aggregated by agent |
| 📊 Monitor | `/api/monitor` | ✅ System stats | agents_online, memory_usage, load |
| 🎟️ Tickets | `/api/tickets` | ✅ 65 tickets | All fields populated; closed/open mix |
| 🛠️ Skills | `/api/skills` | ✅ 11 skills | Shell, browser, file_read, etc. |
| 👥 Agents | `/api/agents` | ✅ 15 agents | Including Nine, Ghost, Grok |
| 📁 Sandpits | `/api/sandpits` | ✅ Agent workspaces | 0 files (expected — sandpits empty) |

---

## 🚀 NEXT STEPS (IN ORDER)

### Phase 1 — Immediate Fixes (This Session)

**BRK-001: Docs Tile**
- [ ] Create `/home/seven/swarm/docs/html/` directory
- [ ] Convert key `.md` files to `.html`:
  - `PROJECT.md` → `project.html`
  - `ARCHITECTURE.md` → `architecture.html`
  - `BUGS.md` → `bugs.html`
- [ ] Update `/api/docs` endpoint to verify directory
- [ ] Test Docs tile loads files

**BRK-002: Chat POST Endpoint**
- [ ] Test `/api/chat` with message → check timeout
- [ ] Verify Ollama is running: `curl http://127.0.0.1:11434/api/tags`
- [ ] If timeout: add 5s timeout + fallback response
- [ ] If Ollama missing: add health check endpoint

**BRK-003: Terminal Tile**
- [ ] Verify `executeCommand()` JS function (terminal_ui_v2.html line 724)
- [ ] Check mapping to `/api/hands/run` or `/api/shell/execute`
- [ ] Test with simple command: `whoami`

### Phase 2 — Integration Testing (After Phase 1)

**BRK-004: Nine File Operations**
- [ ] Call `fridays.file_agent.read_sandpit()` from Python directly
- [ ] Call `fridays.file_agent.write_sandpit()` with test data
- [ ] Verify return types are `(ok, content)` tuples

**BRK-005: End-to-End Flows**
- [ ] Email → Ticket → Agent Response → Reply (full round-trip)
- [ ] Discord message → Ticket creation → Response
- [ ] Telegram command → Sandpit file write

---

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
