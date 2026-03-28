# 🎯 AGENT TASK ASSIGNMENTS — FRIDAYS REFINEMENT PHASE

**Date:** 2026-03-28  
**Phase:** Integration & Validation  
**Deadline:** 2026-03-29 (24 hours)  
**Critical Path Blocker:** BRK-002 (Chat POST timeout)

---

## CRITICAL BLOCKER: BRK-002 — CHAT ENDPOINT TIMEOUT

**Status:** 🔴 BLOCKING ALL E2E AGENT TESTING

**Who:** Gemma (Orchestrator Lead) or Twelve (Ghost Layer)  
**Estimated Fix Time:** 15 minutes  
**Impact:** Without this, cannot validate message→response flow

**Exact Issue:**
```
POST /api/chat with {"message": "test"}
  → Hangs indefinitely
  → Reason: orchestrator.ask_agent() has no timeout
  → Ollama /api/generate blocks forever
```

**Required Fix:**
Wrap orchestrator.ask_agent() with 5-second timeout:

```python
import signal

def ask_agent_with_timeout(agent, message, timeout=5):
    def handler(signum, frame):
        raise TimeoutError(f"{agent} timeout")
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)
    try:
        return orchestrator.ask_agent(agent, message)
    except TimeoutError:
        return f"[Agent thinking... response delayed]"
    finally:
        signal.alarm(0)
```

**File to Edit:** `frontend/terminal.py` line 1248  
**Change:** Replace `orchestrator.ask_agent()` with timeout wrapper

**Must Complete Before:** Task #1 starts

---

## TASK ASSIGNMENTS

### TASK #1: MEMORY & SANDPIT SYSTEMS

**Owner:** Nine (Integration Lead)  
**Dependency:** BRK-002 must be fixed first  
**Estimated Time:** 2 hours  
**Status:** 🟡 QUEUED (waiting for BRK-002)

#### Subtasks:

**1.1: Test read_sandpit() operation**
- File: `fridays/file_agent.py`
- Location: Line 45 (read_sandpit function)
- Status from BUG-019: Fixed to return (ok, content) tuples
- What to Test:
  ```python
  from fridays.file_agent import read_sandpit
  ok, content = read_sandpit('/home/seven/swarm/sandpits/shared', 'test.txt')
  assert isinstance(ok, bool), "Should return boolean"
  assert isinstance(content, str), "Should return string content"
  ```

**1.2: Test write_sandpit() operation**
- File: `fridays/file_agent.py`
- Location: Line 67 (write_sandpit function)
- Create test file in shared sandpit
- Verify return format is (ok, message)

**1.3: Verify Nine can write to own sandpit**
- Call: `fridays.file_agent.write_sandpit('/home/seven/swarm/sandpits/nine', 'test_write.txt', 'Nine was here')`
- Verify file created
- Check permissions (Nine should only create; others shouldn't delete)

**1.4: Test proposal system**
- `fridays.sandpits.write_proposal('proposal_test.md', 'Test proposal content')`
- Verify written to `/sandpits/shared/proposals/`
- Call `fridays.sandpits.read_proposal('proposal_test.md')`
- Verify round-trip works

**Report When Done:** Pull request with test results + verification

---

### TASK #2: AGENT MEMORY LOGGING

**Owner:** Sniffles (Memory Auditor)  
**Dependency:** None (can start immediately)  
**Estimated Time:** 1 hour

#### Subtasks:

**2.1: Verify memory_X table structure**
- All memory tables (memory_gemma, memory_llama, etc.) should have:
  - id, agent, memory, importance, source, archived, timestamp
- Database audit already done ✅
- Verify in your memory fetch operations

**2.2: Test log_agent_memory() function**
- File: `utils/database.py`
- Call: `log_agent_memory('gemma', 'Test memory', importance=8, source='test')`
- Verify inserted to memory_gemma table
- Verify timestamp auto-populated
- Verify archived=0 by default

**2.3: Create memory archival logic**
- Memories older than 7 days should be marked archived=1
- Implement in Sniffles audit loop
- Preserve read access (archived memories become read-only)

**Report When Done:** Memory audit test results + archival schedule

---

### TASK #3: TICKET → AGENT → RESPONSE WORKFLOW

**Owner:** Gemma (Director/Orchestrator)  
**Dependency:** BRK-002 must be fixed  
**Estimated Time:** 2 hours

#### Subtasks:

**3.1: Implement timeout wrapper**
- ⚠️ THIS UNBLOCKS EVERYTHING
- Add to `frontend/terminal.py` API endpoint
- Ensure fallback response is human-readable
- Test with actual POST /api/chat call

**3.2: Verify conversation → message relationship**
- Create conversation: `new_conversation('test-source', 'Test subject')`
- Get its ID
- Log messages: `log_message(conv_id, 'user', 'Hello')`
- Verify retrieved via `GET /api/conversations/{id}/messages`

**3.3: Test ticket routing through orchestrator**
- When BRK-002 fixed: send message to chat
- Verify Gemma receives it
- Verify routing decision (web search? browser? shell?)
- Confirm response logged back to conversation

**3.4: Validate Gemma synthesis**
- If multi-agent response: verify Gemma's synthesis is coherent
- Check that all agent inputs are represented
- Verify no hallucinations/contradictions

**Report When Done:** Full message→response logs + synthesis quality check

---

### TASK #4: DISCORD/TELEGRAM INTEGRATION

**Owner:** Discord Bot / Telegram Bot (or assign to Gemma for testing)  
**Dependency:** Tickets system working (Task #3)  
**Estimated Time:** 1.5 hours

#### Subtasks:

**4.1: Restart Discord service**
```bash
sudo systemctl restart swarm-discord
sleep 2
systemctl is-active swarm-discord
```

**4.2: Send test Discord message**
- DM the bot in Discord
- Verify ticket created in system
- Confirm ticket_number format: DC-{conversation_id}
- Check message appears in Fridays chat

**4.3: Test Discord commands**
- `URGENT` — should mark priority=high
- `TAG test` — should add tag
- `SNOOZE 2h` — should snooze ticket

**4.4: Restart Telegram service & test**
- `sudo systemctl restart swarm-telegram`
- Send message to bot in Telegram
- Verify ticket created (format: TG-{conversation_id})
- Test commands same as Discord

**Report When Done:** Integration test results + command response times

---

### TASK #5: EMAIL INGESTION END-TO-END

**Owner:** Email Handler (or Twelve for validation)  
**Dependency:** Tickets system working  
**Estimated Time:** 1.5 hours

**5.1: Send test email to system**
- Email address configured in trusted_senders
- Subject: "Test E2E Email"
- Body: "Does this create a ticket?"

**5.2: Verify ticket creation**
- Query: `SELECT * FROM tickets WHERE sender_email='test@example.com' ORDER BY created_at DESC`
- Confirm question field includes email body
- Verify status=open

**5.3: Check email handler logs**
- Verify in `listener.py` queue processing
- Check for any errors in email_cleaner strip logic
- Confirm librarian triage ran

**5.4: Verify Gemma routing**
- Check ticket's gemma_routing field
- Should contain: needs_web, agents, mode, is_system, etc.
- Confirm routing made sense for test email

**5.5: Confirm response email**
- Verify response sent back to sender
- Check response format (includes ticket number, agent response, etc.)

**Report When Done:** Full email→ticket→response chain with timing logs

---

### TASK #6: PROPOSAL WORKFLOW VALIDATION

**Owner:** Sniffles (Proposal Auditor) or Gemma  
**Dependency:** None (independent)  
**Estimated Time:** 1 hour

**6.1: Review existing proposals**
- List: `GET /api/proposals`
- Should return array with any existing proposals

**6.2: Create test proposal**
- Agent writes to `/sandpits/shared/proposals/test_proposal.md`
- Content includes: problem statement, solution, impact

**6.3: Sniffles audits proposal**
- Read proposal
- Check for: clear language, no hallucinations, feasibility
- Mark PASS/WARN/FLAG

**6.4: Proposal appears in UI**
- Confirm visible in Fridays "Proposals" tile
- Verify metadata (author, date, status)

**Report When Done:** Proposal flow validation + audit results

---

## DEPENDENCIES & CRITICAL PATH

```
BRK-002 (Chat Timeout) ← BLOCKS EVERYTHING
        ↓
    FIXED ✓
        ↓
Task #3 (Ticket→Response) ← Must complete before #4, #5
        ├─ Task #4 (Discord/Telegram)
        ├─ Task #5 (Email E2E)
        └─ Task #6 (Proposals)
        
Task #1 (Memory/Sandpits) — Independent, can start now
Task #2 (Memory Logging) — Independent, can start now
```

**Critical Path Duration:** BRK-002 (15min) + Task #3 (2h) = **2.25 hours minimum**

---

## VALIDATION CHECKLIST

Before marking "REFINEMENT PHASE COMPLETE":

- [ ] BRK-002 fixed; chat timeout resolved
- [ ] All 19 E2E tests PASS (currently 18 PASS, 1 blocked)
- [ ] Message→Response cycle validated (Task #3)
- [ ] Email→Ticket→Response tested (Task #5)
- [ ] Discord & Telegram integrations verified (Task #4)
- [ ] Memory auditing running (Task #2)
- [ ] Proposal system working end-to-end (Task #6)
- [ ] File operations (sandpits) validated (Task #1)
- [ ] All changes committed to GitHub
- [ ] CHANGELOG updated with all fixes
- [ ] No new timeout/hang issues discovered

**Success Criteria:** All tests PASS; zero blockers for Nine integration audit

---

## RESOURCE ALLOCATION

| Agent | Primary Task | Secondary Task | Status |
|-------|-------------|-----------------|--------|
| Gemma | Fix BRK-002 + Task #3 | Oversee Task #4 | READY |
| Nine | Task #1 (Sandpits) | Code integration | READY |
| Sniffles | Task #2 (Memory) + Task #6 | Proposal audit | READY |
| Duck | Quality gate on responses | Review Task #3 | READY |
| Discord Bot | Task #4 (Discord) | — | OFFLINE (restart needed) |
| Telegram Bot | Task #4 (Telegram) | — | OFFLINE (restart needed) |
| Eight | Domain validation for SAP cases | — | AVAILABLE |

---

## SIGN-OFF

**Created by:** Agent Twelve (Ghost Layer)  
**Ready for Execution:** NOW  
**No Questions Asked:** Agents have all context needed  
**Timeline:** Target completion 2026-03-29 10:00 UTC  
**Next Milestone:** Nine Integration Audit (pending all tasks complete)
