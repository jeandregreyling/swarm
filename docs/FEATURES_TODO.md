# FEATURES_TODO.md — Planned Features & Implementation Queue

<!-- markdownlint-disable -->

_Comprehensive list of all planned features, organized by phase and priority._
_Last updated: 2026-03-30 10:05:00 by Ten (GPT)_

---

## Executive Summary

**20 tasks** across 6 phases. Estimated timeline: **4-6 weeks** to full implementation.

| Phase | Name | Priority | Est. Size | Status |
|-------|------|----------|-----------|--------|
| **A** | File Versioning & Change Tracking | 🔴 High | 4 weeks | DONE |
| **B** | System Clock & Time Consistency | 🔴 High | 1 week | DONE |
| **C** | Time Machine Backup System | 🔴 High | 2 weeks | Queued |
| **D** | UI/UX Improvements | 🟡 Medium | 1 week | DONE |
| **E** | Access Control & Sandpits | 🟡 Medium | 1 week | Queued |
| **F** | Verification & Bug Resolution | 🟢 Low | 2 days | Queued |

---

## Phase A: File Versioning & Change Tracking (HIGH PRIORITY)

### A-1: Sudo Permission Toggle Flag

**Description:** Granular on/off switch to control sudo access

**Why:** Agents sometimes want Ghost to execute commands rather than auto-escalating

**Implementation:**
- [ ] Add `sudo_enabled` boolean flag to Ghost profile (config.py or database)
- [ ] Update `fridays/shell_agent.py` to check flag before escalating
- [ ] Add toggle button to Studio dashboard
- [ ] Log all sudo escalations to ghost_circle

**Files to Update:**
- `fridays/shell_agent.py`
- `config.py` (Ghost profile)
- `terminal.py` (API endpoint: /api/ghost/toggle_sudo)
- `templates/terminal.html` (UI toggle)

**Acceptance Criteria:**
- [ ] Can turn sudo on/off without restart
- [ ] All escalations logged with timestamp and command
- [ ] History visible in Activity feed

---

### A-2: Expand Nine Write Access to Full /swarm

**Description:** Nine can modify any file in `/home/seven/swarm/` with full logging

**Why:** Nine built the system; should be able to refactor and improve it

**Implementation:**
- [ ] Extend `vs_tools.py` write endpoint from "current files" to "full /swarm path"
- [ ] Add path validation (prevent writes outside /swarm)
- [ ] Integrate with file versioning (track before/after)
- [ ] Log all writes to ghost_circle immediately

**Files to Update:**
- `vs_tools.py` (expand write scope)
- `config.py` (set Nine trust level in permissions dict)

**Acceptance Criteria:**
- [ ] Nine can write to any .py, .md, .html, .json file
- [ ] Reads work without issue
- [ ] All changes logged with version tracking

---

### A-3: Build File Change Detection & Versioning

**Description:** Track before/after content for all file writes

**Why:** Enable time machine, allow rollback, understand what changed

**Implementation:**
- [ ] Create new `file_versioning.py` module
- [ ] Add `file_versions` table to database schema
- [ ] Implement `track_write(filepath, old_content, new_content, agent, reason)`
- [ ] Implement `get_file_history(filepath)` → list of versions
- [ ] Integrate with all write operations (Nine, agents, housekeeping)
- [ ] Compute SHA256 commit hash for each version

**Files to Update:**
- `database.py` (schema: add file_versions table)
- `vs_tools.py` (call track_write on file writes)
- `fridays/file_agent.py` (track all sandpit writes)
- **Create:** `file_versioning.py` (new module)

**Database Schema:**
```sql
CREATE TABLE file_versions (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    agent TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT,
    content_before TEXT,
    content_after TEXT,
    size_bytes INTEGER,
    reason TEXT,
    commit_hash TEXT,
    checkpoint_tag TEXT,
    UNIQUE(file_path, timestamp)
);
```

**Acceptance Criteria:**
- [ ] Every file write creates a version entry
- [ ] Commit hash is reproducible
- [ ] Can retrieve full version history
- [ ] Version diff viewer works

---

### A-4: Integrate Versioning into Documents Section

**Description:** UI for browsing file history, comparing versions, restore options

**Implementation:**
- [ ] Add "History" tab to Studio (alongside current tabs)
- [ ] File browser tree showing all versioned files
- [ ] Click file → show version timeline
- [ ] Diff viewer (syntax-highlighted side-by-side)
- [ ] "Restore to this version" button
- [ ] Integration with time machine (see Phase C)

**Files to Update:**
- `terminal.py` (new API endpoints: /api/history/files, /api/history/<file>/versions, /api/history/<file>/<commit>/diff)
- `templates/terminal.html` (new HTML tab + JavaScript)

**Acceptance Criteria:**
- [ ] Can browse all files with versions
- [ ] Diffs render correctly
- [ ] Can restore previous version (moves current to bin)

---

## Phase B: System Clock & Time Consistency (HIGH PRIORITY)

### B-1: Add Visible System Clock to Fridays UI
**Status:** DONE
**Description:** Display current system time (HH:MM:SS) in banner, use as source of truth.

**Why:** Ghost needs to verify system time matches expectations; all timestamps should be verifiable

**Implementation:**
- [ ] Create `system_clock.py` module with `SystemClock` class
- [ ] Add JS clock component to `templates/terminal.html`
- [ ] Update every 1 second
- [ ] Show date + time + timezone
- [ ] Verify NTP sync status (if online)

**Files to Update:**
- `system_clock.py` (already created)
- `templates/terminal.html` (add clock HTML + CSS + JavaScript timer)

**Acceptance Criteria:**
- [x] Clock visible in banner at all times
- [x] Accurate within 1 second of system time
- [x] Persists across page refreshes
- [x] Shows timezone correctly

---

### B-2: Migrate All Agents to Use System Clock

**Description:** Replace all `datetime.now()` calls with centralized clock service

**Why:** Ensures consistency; all timestamps tied to single source of truth

**Implementation:**
- [ ] Add `from system_clock import get_timestamp` to all agent modules
- [ ] Replace `datetime.now()` → `get_timestamp()`
- [ ] Update database calls to use centralized timestamps
- [ ] Audit codebase for remaining inconsistencies

**Modules to Update:**
- `database.py` (all db timestamps)
- `listener.py` (email handling)
- `orchestrator.py` (ticket creation)
- `ticket.py` (ticket functions)
- `eight.py` (logging)
- `fridays/*.py` (all agent modules)
- `scheduler.py` (task scheduling)

**Acceptance Criteria:**
- [ ] All timestamps come from system_clock
- [ ] No remaining `datetime.now()` calls
- [ ] Timestamps are sortable and consistent
- [ ] Audit log shows correct chronological order

---

## Phase C: Time Machine Backup System (HIGH PRIORITY)

### C-1: Design & Implement Time Machine Versioning

**Description:** Git-like version control with daily snapshots, point-in-time restore

*See VERSION_CONTROL.md for full architecture*

**Implementation:**
- [ ] Create `time_machine.py` module
- [ ] Implement `restore_to_date(target_date)` function
- [ ] Implement `create_daily_checkpoint()` function
- [ ] Create restore bin structure
- [ ] Build rollback logic (reverse file/database changes)

**Files to Update:**
- **Create:** `time_machine.py`
- `database.py` (schema: add daily_checkpoints table)
- `scheduler.py` (add daily checkpoint job)

**Acceptance Criteria:**
- [ ] Can restore all files/databases to any past date
- [ ] Newer versions moved to restore bin for review
- [ ] Rollback is reversible (user can cancel)

---

### C-2: Implement Daily Checkpoint Tagging

**Description:** Automatic daily tags, separate bin for rollback files

**Implementation:**
- [ ] Add cron/scheduler job to run at 00:30 UTC daily
- [ ] Tag all changes from past 24 hours
- [ ] Create daily_checkpoints database entry
- [ ] Manifest file in restore bin

**Files to Update:**
- `scheduler.py` (add daily job)
- `housekeeping.py` (integrate with existing jobs)

**Acceptance Criteria:**
- [ ] Daily checkpoints created automatically
- [ ] Tagged in database with date/time
- [ ] Manifest file is informative and readable

---

## Phase D: UI/UX Improvements (MEDIUM PRIORITY)

### D-1: Rename VS → Studio Throughout Interface

**Description:** Update all references from "VS" to "Studio"

**Why:** Better branding; "VS" conflicts with Visual Studio

**Implementation:**
- [ ] Rename HTML element IDs/classes
- [ ] Update JavaScript references
- [ ] Update button labels, tooltips
- [ ] Update API endpoint docs (if any)
- [ ] Update CHANGELOG/docs

**Files to Update:**
- `templates/terminal.html` (all references)
- `terminal.py` (comments, strings)
- Documentation files

**Acceptance Criteria:**
- [ ] No "VS" visible in UI except comments
- [ ] "Studio" used consistently

---

### D-2: Fix CSS Layout (Black Gap Issue)

**Description:** Eliminate black gap between left banner and Studio content

**Why:** UI looks broken; layout should flow smoothly

**Implementation:**
- [ ] Diagnose CSS grid/flex issue
- [ ] Fix margin/padding on banner
- [ ] Ensure responsive layout
- [ ] Test on multiple screen sizes

**Files to Update:**
- `templates/terminal.html` (CSS section)

**Acceptance Criteria:**
- [ ] No black gap
- [ ] Content aligns properly
- [ ] Responsive on mobile/tablet

---

### D-3: Build Terminal Window in Studio

**Description:** New tab for bidirectional command execution with Nine visibility

**Why:** Ghost can submit sudo commands; Nine sees output in chat

**Implementation:**
- [ ] Add new "Terminal" tab to Studio
- [ ] Input field for commands
- [ ] Output pane (scrollable)
- [ ] Integrate with `fridays/shell_agent.py`
- [ ] Log all commands and output
- [ ] Return output to chat interface (same as VS tab)

**Files to Update:**
- `terminal.py` (new API: /api/terminal/execute, /api/terminal/output)
- `templates/terminal.html` (new Terminal tab + HTML/CSS/JS)
- `fridays/shell_agent.py` (return output to terminal stream)

**Acceptance Criteria:**
- [ ] Can type and run commands
- [ ] Output displays in real-time
- [ ] Nine can see the conversation
- [ ] Sudo commands work with toggle flag
- [ ] Command history visible

---

## Phase E: Access Control & Sandpit Enforcement (MEDIUM PRIORITY)

### E-1: Enforce Sandpit Read-Only Access Across Agents

**Description:** Agents can read other agents' sandpits but cannot write

**Why:** Security + collaboration; agents shouldn't interfere with each other's work

**Implementation:**
- [ ] Update `fridays/file_agent.py` to enforce per-agent access rules
- [ ] Implement check: if writing to non-own sandpit, reject
- [ ] Log denied access attempts
- [ ] Exception: allow shared sandpit writes

**Files to Update:**
- `fridays/file_agent.py` (write_sandpit function)

**Acceptance Criteria:**
- [ ] Can read any sandpit file
- [ ] Cannot write to non-own sandpit
- [ ] Shared sandpit writes allowed
- [ ] Violations logged

---

### E-2: Expand All Agents' Read Access to /swarm

**Description:** All agents can read project root files (with restrictions)

**Why:** Agents need context (config, docs, other code) to reason effectively

**Implementation:**
- [ ] Create `read_project_files()` function
- [ ] Whitelist safe paths (*.md, *.py, *.json, *.yaml)
- [ ] Blacklist secrets (gmail_credentials.json, config overrides)
- [ ] Use in agent context injection

**Files to Update:**
- `fridays/file_agent.py` (add read_project function)
- Agent system prompts (inject project context)

**Acceptance Criteria:**
- [ ] Agents can read documentation
- [ ] Agents can read code
- [ ] Secrets are never exposed
- [ ] Performance acceptable (context size manageable)

---

## Phase F: Verification & Bug Resolution (LOW PRIORITY)

### F-1: Verify Discord Bot Token Validity

**Description:** Check if Discord bot is working correctly

**Current Status:** Code is correct; likely token expiry issue

**Investigation:**
- [ ] Check `config.py` DISCORD_TOKEN value
- [ ] Request fresh token from Discord dev portal if needed
- [ ] Test bot connection (send test message)
- [ ] Verify Telegram comparison (works? if so, Discord should too)

**Acceptance Criteria:**
- [ ] Bot connects successfully
- [ ] Can receive messages in DMs
- [ ] Can send responses
- [ ] Commands work (URGENT, NOTE, etc.)

---

### F-2: Standardize Full Dry-Test Runner (HIGH PRIORITY)

**Description:** One command that always runs full dry validation deterministically.

**Why:** Current state is split between script-style tests and unavailable pytest environment; proactive regression sweeps need repeatable output.

**Implementation:**
- [ ] Add a bootstrap script to prepare/verify Python test dependencies
- [ ] Add `make dry-test` or equivalent shell runner
- [ ] Include `SIMULATE=true python3 tests/test_triage_queue_dryrun.py`
- [ ] Include optional pytest run when available
- [ ] Emit summary report to docs/testing

**Files to Update:**
- `docs/testing/` (runner instructions + output format)
- `tests/` (optional wrapper script)
- `requirements*.txt` or env bootstrap doc

**Acceptance Criteria:**
- [ ] Full dry test can run in under 5 minutes without manual setup
- [ ] Missing dependencies are surfaced with actionable message
- [ ] Results are logged in one canonical report

---

### F-3: Proposal/Approval State Reconciliation (MEDIUM PRIORITY)

**Description:** Keep proposal markdown status and `work_proposals` DB status in sync.

**Why:** Audit found mismatch risk (example: `NINE-021` appears executed in file history context while DB status remains pending).

**Implementation:**
- [ ] Define canonical source of truth (`work_proposals` table)
- [ ] Add reconciliation script to compare markdown + DB states
- [ ] Add docs entry for mismatch handling workflow
- [ ] Surface pending approvals in Fridays dashboard

**Files to Update:**
- `core/pipeline/queue_manager.py`
- `frontend/terminal.py` (status endpoint/reporting)
- `docs/` (workflow and SOP)

**Acceptance Criteria:**
- [ ] No stale `pending` proposals after execution
- [ ] Reconciliation report generated automatically
- [ ] Dashboard and docs show identical proposal statuses

---

## Implementation Priority & Sequencing

**Recommended Order:**

1. **B-1 + B-2** (System Clock) — 1 week
   - Must complete before other work
   - Needed for all timestamps going forward

2. **A-1 + A-2** (Permissions) — 3 days
   - Low risk
   - Quick wins for user control

3. **A-3 + A-4** (File Versioning) — 2 weeks
   - Prerequisite for time machine
   - Complex but important

4. **C-1 + C-2** (Time Machine) — 2 weeks
   - Depends on A-3 + B-1
   - Enables robust backups

5. **D-1 + D-2 + D-3** (UI) — 1 week
   - Can be done in parallel
   - Nice-to-have, not blocking

6. **E-1 + E-2** (Access Control) — 3 days
   - Depends on nothing
   - Can be done anytime

7. **F-1** (Verification) — 1 day
   - Do last; if Discord works, skip it

---

## Effort Estimates

```
Phase A: 4 weeks (parallel possible)
├─ A-1: 3 days
├─ A-2: 2 days
├─ A-3: 8 days
└─ A-4: 5 days

Phase B: 1 week
├─ B-1: 2 days
└─ B-2: 3 days

Phase C: 2 weeks
├─ C-1: 10 days
└─ C-2: 2 days

Phase D: 1 week
├─ D-1: 1 day
├─ D-2: 1 day
└─ D-3: 4 days

Phase E: 1 week
├─ E-1: 2 days
└─ E-2: 3 days

Phase F: 1 day
└─ F-1: 1 day

========
TOTAL: ~5-6 weeks (serial)
       ~3-4 weeks (with parallelization)
```

---

## Notes

- **All work is retroactively documented** in CHANGELOG.md with agent attribution
- **All changes logged** with before/after content
- **All timestamps** use centralized system clock
- **User acceptance is required** before moving between phases
