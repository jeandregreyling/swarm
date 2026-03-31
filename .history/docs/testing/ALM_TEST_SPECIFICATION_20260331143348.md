# 📋 FRIDAYS ALM TEST CASE SPECIFICATION

**Date:** 2026-03-28  
**Version:** 1.0 — Refinement Phase  
**Audience:** Agent Twelve (Test Automation), Nine (Integration), Agents (Execution)  
**Status:** READY FOR AGENT EXECUTION

---

## 2026-03-31 Addendum — Chat Quality Hardening

Scope added for Fridays chat quality and identity-aware skill behavior:

| REQ ID | Requirement | Test Case | Status | Owner |
|--------|-------------|-----------|--------|-------|
| REQ-CHAT-001 | Skill output does not bleed into next chat context | CQ-1 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-002 | SKILL command response shape is stable | CQ-2 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-003 | SKILL response returns identity context | CQ-3 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-004 | Denied user/skill pair is blocked with 403 | CQ-4 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-005 | Ghost-layer memory API available for Nine/Ten | CQ-5 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-006 | Ten prompt style guardrails loaded | CQ-6 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-007 | terminal.py compiles after chat hardening | CQ-7 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-008 | Pending chat jobs status endpoint available | CQ-8 | ✅ PASS | Nine/Copilot |
| REQ-CHAT-009 | Long-running chat requests persist until completion | CQ-9 | ✅ PASS | Nine/Copilot |

Execution evidence:
- `python3 tests/test_chat_quality.py` -> 9 PASS, 0 FAIL, 0 SKIP
- `python3 tests/test_e2e_fridays.py` -> 21 PASS, 0 FAIL, 0 ERROR, 0 SKIP


---

## REQUIREMENTS TRACEABILITY MATRIX

| REQ ID | Requirement | Test Case | Status | Owner |
|--------|-------------|-----------|--------|-------|
| REQ-001 | Chat history accessible | A-1-001 | ✅ PASS | Twelve |
| REQ-002 | Agent message processing | A-2-001 | 🔴 BLOCKED | Orchestrator |
| REQ-003 | Memory search functional | A-3-001 | ✅ PASS | Twelve |
| REQ-004 | System monitoring available | A-4-001 | ✅ PASS | Monitor |
| REQ-005 | Ticket management operational | A-5-001 | ✅ PASS | Database |
| REQ-006 | Skill system available | A-6-001 | ✅ PASS | Skills |
| REQ-007 | Agent roster visible | A-7-001 | ✅ PASS | Database |
| REQ-008 | Knowledge base accessible | A-8-001 | ✅ PASS | Docs |
| REQ-009 | Sandpit workspaces ready | A-9-001 | ✅ PASS | Sandpits |
| REQ-010 | Shell execution operational | B-1,B-2 | ✅ PASS | Shell |
| REQ-011 | Infrastructure healthy | C-1 | ✅ PASS | System |

---

## TEST CASE SPECIFICATIONS

### TEST CASE A-1-001: Load Chat History

**Category:** Functional / Read  
**Priority:** CRITICAL  
**Pre-Condition:** Fridays service running, database populated with conversations  

**Steps:**
1. Call GET /api/conversations
2. Parse response array
3. Verify each object has: id, title, source, created_at/timestamp
4. Count total conversations

**Expected Result:**
- HTTP 200 response
- Array of conversation objects (40+ expected)
- All required fields present
- Timestamps in ISO format

**Actual Result (Execution):**
```
✅ PASS
Response: Array of 40 conversation objects
Fields: id, created_at, timestamp (aliased), title (aliased), source
Sample: {
  "id": 144,
  "created_at": "2026-03-28 11:46:58",
  "timestamp": "2026-03-28 11:46:58",
  "title": "terminal-ui",
  "source": "test"
}
```

**Notes:** Field aliasing working correctly (created_at → timestamp, subject → title)

---

### TEST CASE A-2-001: Send Chat Message (Timeout)

**Category:** Functional / Write  
**Priority:** CRITICAL  
**Pre-Condition:** Chat endpoint running, orchestrator available

**Steps:**
1. POST /api/chat with message: "hello world"
2. Expect response within 10 seconds
3. Verify response contains: ok, response, conversation_id
4. Confirm message logged to database

**Expected Result:**
- HTTP 200 response
- JSON with {ok: true, response: "...", conversation_id: N}
- Response within 5-10 seconds
- Message logged to conversations table

**Actual Result (Execution):**
```
⏱️  TIMEOUT (>10s)
Root Cause: orchestrator.ask_agent('gemma') blocks indefinitely
Pipeline: POST → new_conversation() ✅ → log_message() ✅ → ask_agent() ⏰

Call Stack Analysis:
  ask_agent('gemma', message)
    → AGENTS['gemma'].ask() 
    → Ollama /api/generate (BLOCKED - no timeout wrapper)

Status: BLOCKING FULL E2E FLOW
```

**Blocker Resolution Needed:**
- Add 5s timeout to ask_agent() with fallback
- OR async wrapper with non-blocking response
- OR mock agent for testing

---

### TEST CASE A-3-001: Memory Search

**Category:** Functional / Query  
**Priority:** HIGH

**Steps:**
1. Call GET /api/agents/memories/query?q=test
2. Verify response structure: {query, agents, results}
3. Verify results aggregated by agent

**Expected Result:**
- HTTP 200
- Response shape: {query: "test", agents: [...], results: {agent_name: [...]}}
- Cross-agent memory search working

**Actual Result (Execution):**
```
✅ PASS
Response structure:
{
  "query": "test",
  "agents": ["gemma", "llama", "qwen", "nine", ...],
  "results": {
    "gemma": [memory_objects...],
    "nine": [memory_objects...],
    ...
  }
}
```

---

### TEST CASE A-5-001: Load Tickets

**Category:** Functional / Query  
**Priority:** CRITICAL

**Steps:**
1. GET /api/tickets
2. Verify response is array of ticket objects
3. Check required fields: ticket_number, status, sender_email, question, created_at
4. Count open vs closed

**Expected Result:**
- HTTP 200
- Array of 65+ ticket objects
- Fields: ticket_number, status (open/closed), created_at, sender_email
- Sample mix: 20 open, 45 closed (approximately)

**Actual Result (Execution):**
```
✅ PASS
Tickets returned: 65
Status distribution:
  - open: 20
  - closed: 45
Sample:
{
  "ticket_number": "TICKET-117",
  "status": "closed",
  "created_at": "2026-03-26 02:05:58",
  "sender_email": "jgreyling@deloitte.com.au",
  "question": "Subject: System Refresh\n\nReview the attached document...",
  "note_count": 1,
  "duck_result": "YES",
  "snooze_count": 0
}
```

---

### TEST CASE B-1-001: Shell Command Execution

**Category:** Functional / Action  
**Priority:** HIGH

**Steps:**
1. POST /api/hands/run with command: "whoami"
2. Verify response contains: command, ok, output
3. Check output matches expected result

**Expected Result:**
- HTTP 200
- {ok: true, command: "whoami", output: "seven\n"}
- Command executes without error

**Actual Result (Execution):**
```
✅ PASS
Response:
{
  "command": "whoami",
  "ok": true,
  "output": "seven\n"
}
```

---

## DATABASE INTEGRITY AUDIT RESULTS

| Table | Status | Row Count | Issues |
|-------|--------|-----------|--------|
| memory | ✅ OK | 67 | Columns: id, agent, memory, importance, source, archived, timestamp, created_at, updated_at, verified, cached |
| memory_gemma | ✅ OK | 42 | All columns present |
| memory_llama | ✅ OK | 42 | All columns present |
| memory_qwen | ✅ OK | 23 | All columns present |
| memory_nine | ✅ OK | 36 | All columns present |
| ticket_notes | ✅ OK | 56 | Foreign key integrity valid |
| tickets | ✅ OK | 65 | All state transitions valid |
| conversations | ✅ OK | 40 | All referenced by messages |

**Verdict:** ✅ Database integrity 100% healthy

---

## SANDPIT STRUCTURE AUDIT

```
/home/seven/swarm/sandpits/
├── gemma/          — 2 files
├── llama/          — 2 files
├── qwen/           — 1 file
├── eight/          — 1 file
├── librarian/      — 1 file
├── sniffles/       — 0 files (audit-only, no write access)
├── nine/           — 0 files (ready for integration)
├── grok/           — 0 files (ready for activation)
├── shared/         — 14 files (proposals + collaboration)
└── [Total]         — 21 files across 10 agent spaces
```

**Verdict:** ✅ Sandpit infrastructure ready; agents can write/read

---

## CRITICAL BLOCKER: BRK-002 — Chat POST Timeout

### Problem Statement
- Endpoint: POST /api/chat
- Issue: Hangs indefinitely; no response after 30+ seconds
- Impact: Cannot test message→response cycle; blocks full E2E flow
- Root Cause: orchestrator.ask_agent() has no timeout wrapper

### Call Trace
```
POST /api/chat
  ├─ new_conversation('terminal-ui', message) ✅ (instant)
  ├─ log_message(conv_id, 'user', message) ✅ (instant)
  └─ ask_agent('gemma', message) ⏰ (TIMEOUT)
      └─ Ollama /api/generate (waiting for model output, no timeout)
```

### Immediate Solutions (Priority Order)

**Solution 1: Add Timeout Wrapper (5 min)**
```python
from signal import alarm, signal, SIGALRM

def ask_agent_with_timeout(agent_name, message, timeout_sec=5):
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Agent {agent_name} did not respond in {timeout_sec}s")
    
    signal(SIGALRM, timeout_handler)
    signal.alarm(timeout_sec)
    try:
        return orchestrator.ask_agent(agent_name, message)
    except TimeoutError:
        return f"[TIMEOUT] {agent_name} thinking... (response may come later)"
    finally:
        signal.alarm(0)
```

**Solution 2: Async Wrapper with Queue (15 min)**
- Execute ask_agent() in background thread
- Return immediate response: "Processing..."
- Store result in conversation when ready
- Frontend polls for updated response

**Solution 3: Mock Agent for Testing (10 min)**
- Return deterministic response for testing
- Real orchestrator still runs; test mode available

### Who Should Fix
**Owner:** Orchestrator (Gemma or Twelve)  
**Blocking:** Full E2E agent testing  
**Must Have Before:** Agent integration validation

---

## TEST COVERAGE SUMMARY

| Category | Total | Pass | Fail | Blocked | Coverage |
|----------|-------|------|------|---------|----------|
| API Endpoints | 9 | 8 | 0 | 1 | 88% |
| Terminal Ops | 2 | 2 | 0 | 0 | 100% |
| Infrastructure | 3 | 3 | 0 | 0 | 100% |
| Database | 5 | 5 | 0 | 0 | 100% |
| **TOTAL** | **19** | **18** | **0** | **1** | **95%** |

---

## HANDOFF: AGENT TEST RESPONSIBILITIES

### For Gemma (Orchestrator Owner)
- [ ] Fix BRK-002 — Add timeout to ask_agent()
- [ ] Verify conversation → message flow
- [ ] Test message logging accuracy
- [ ] Validate response synthesis

### For Nine (Integration Lead)
- [ ] Execute file operations in sandpits
- [ ] Validate read_sandpit() / write_sandpit() return types
- [ ] Test memory write with log_agent() function
- [ ] Confirm proposal system end-to-end

### For Eight (SAP Specialist)
- [ ] Verify memory loading from database
- [ ] Test knowledge application in responses
- [ ] Validate scenario-based memory updates

### For Duck (Quality Gate)
- [ ] Review conversation message quality
- [ ] Validate ticket note content
- [ ] Approve proposals before shareable

### For Sniffles (Memory Auditor)
- [ ] Run sandpit audit on all agents
- [ ] Memory importance scoring validation
- [ ] Contradiction detection in new memories
- [ ] Archive old memories (7+ day retention policy)

### For Terminal Bots (Discord/Telegram)
- [ ] Message → Ticket creation
- [ ] Command parsing (URGENT, TAG, SNOOZE)
- [ ] Response delivery back to chat platform

---

## TEST EXECUTION LOG

**Started:** 2026-03-28 23:42 UTC  
**Completed:** 2026-03-28 23:55 UTC  
**Duration:** 13 minutes  
**Environment:** swarm-terminal service on port 5050  
**Database:** swarm_memory.db (production data)

**Tests Executed:**
- Suite A (API Endpoints): 9 tests → 8 PASS, 1 TIMEOUT
- Suite B (Terminal): 2 tests → 2 PASS
- Suite C (Infrastructure): 3 tests → 3 PASS
- Suite D (Database): 5 tests → 5 PASS

**Issues Found:**
- 1 CRITICAL (BRK-002: Chat POST timeout)
- 1 HIGH (BRK-004: Agents disconnected — expected)
- 0 REGRESSION issues

**Build Quality:** ✅ PRODUCTION READY (except Chat flow)

---

## NEXT TEST PHASE: FULL E2E SCENARIOS

When BRK-002 is fixed:

1. **Scenario 1: Email Ingestion**
   - Send email to test@domain.com
   - Verify ticket created in DB
   - Confirm Gemma routing
   - Validate agent response

2. **Scenario 2: Message to Ticket**
   - Send chat message
   - Confirm conversation logged
   - Verify agent processes through orchestrator
   - Confirm response returned

3. **Scenario 3: Proposal Workflow**
   - Agent writes proposal to sandpits/shared/proposals/
   - Sniffles audits
   - Proposal appears in proposals list
   - Duck reviews, approves

4. **Scenario 4: Multi-Agent Debate**
   - Chat message triggers multi-agent debate
   - Verify each agent contributes
   - Confirm Gemma synthesizes
   - Response includes all perspectives

5. **Scenario 5: External Integration**
   - Discord command sent
   - Telegram message sent
   - Both create tickets with correct metadata
   - Both receive responses routed back

---

**Status:** ✅ READY FOR AGENT HANDOFF
