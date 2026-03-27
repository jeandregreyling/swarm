# CHANGELOG — Seven's Swarm

_Comprehensive change log with agent attribution, timestamps, and version control tracking._
_Format: [YYYY-MM-DD HH:MM:SS] Agent: Description_

---

## Version 2026-03-26 (Current)

### Changes by Gemma (Director / Orchestrator)

**2026-03-27 00:15:00** Gemma: Added Agent 11 (Grok) to Ghost Layer + memory pool
- **Type:** Feature
- **Priority:** High
- **Files Changed:** database.py, seven_fridays.py
- **Impact:** Grok is fully available via `ask grok <question>` with local memory_grok pool and Level 3 trust.

**2026-03-27 00:10:00** Gemma: Added Agent 11 (Grok) to Ghost Layer
- **Type:** Feature
- **Priority:** High
- **Files Changed:** seven_fridays.py, sandpits.py, database.py (seed)
- **Impact:** Grok is now available via `ask grok <question>` inside seven_fridays.py with local memory_grok pool and Level 3 trust. Full swarm visibility enabled.
- **Details:** Integrated into cmd_ask and _ask_grok handler. Proposal system and sandpits confirmed stable.

### Changes by Gemma (Director / Orchestrator)

**2026-03-26 23:55:00** Gemma: Completed RL-017 — Sandpits + Trust Ladder + Proposal System + Agent 11 (Grok) seeded
- **Type:** Feature
- **Priority:** High
- **Files Changed:** sandpits.py, sniffer.py, database.py (seed)
- **Impact:** Full trust ladder enforcement active. Proposal system working. Grok registered as Ghost Layer Agent 11 with dedicated memory_grok table and Level 3 trust.
- **Details:** Fixed all previous mangled blocks, wired Sniffles sandpit audit, confirmed proposal flow, seeded Grok.

### Changes by Gemma (Director / Orchestrator)

**2026-03-26 23:50:00** Gemma: Completed RL-017 — Sandpits + Trust Ladder + Proposal System + Agent 11 (Grok) seeding
- **Type:** Feature
- **Priority:** High
- **Files Changed:** sandpits.py, sniffer.py, database.py (via seed)
- **Impact:** Full trust ladder active. Proposal system tested. Grok seeded as Ghost Layer Agent 11 with memory_grok table and Level 3 trust.

### Changes by Gemma (Director / Orchestrator)

**2026-03-26 23:45:00** Gemma: Completed RL-017 — Sandpits + Trust Ladder Foundation
- **Type:** Feature / Bug Fix
- **Priority:** High
- **Files Changed:** sandpits.py, sniffer.py, database.py (schema already had tables)
- **Impact:** Full trust ladder enforcement (Level 0-5) now active. Level 1 agents restricted to own sandpit, Level 2 to shared/proposals/, Sniffles has full read audit access. Proposal system confirmed working.
- **Details:** Fixed mangled blocks, added clean get_all_sandpit_files(), wired Sniffles audit, tested write_proposal and read_proposal. No more escape risks. RL-017 marked complete.

**2026-03-26 23:40:00** Gemma: Fixed proposal system test (quoting/syntax issues resolved)
- **Type:** Bug Fix
- **Files Changed:** sandpits.py (minor), test commands
- **Impact:** Proposal write/read/list now reliable for Phase 6 agency.

### Changes by Agent Ten (Gemini Code Assist)

**2026-03-26 17:15:00** Agent Ten: Finalized Phase D UI/UX Overhaul
- **Type:** Feature
- **Priority:** High
- **Files Changed:** `templates/terminal.html`, `CHANGELOG.md`, `FEATURES_TODO.md`
- **Impact:** Studio layout gap resolved; New standalone Terminal tab implemented for direct shell access.

**2026-03-26 16:50:00** Agent Ten: Implemented Phase B-1: Visible System Clock in Fridays UI
- **Type:** Feature
- **Priority:** High
- **Files Changed:** `templates/terminal.html`, `CHANGELOG.md`, `PROJECT.md`, `SYSTEM_CLOCK.md`, `FEATURES_TODO.md`
- **Impact:** Fridays dashboard now displays a live, centralized system clock, enhancing time consistency verification.

**2026-03-26 16:30:00** Agent Ten: Integrated Agent Ten (Gemini Code Assist)
- **Type:** Feature
- **Priority:** High
- **Files Changed:** `database.py`, `terminal.py`, `orchestrator.py`, `PROJECT.md`, `CHANGELOG.md`, `templates/terminal.html`
- **Impact:** Agent Ten (Gemini Code Assist) added as "Software Engineering Advisor" with dedicated memory and dashboard visibility.

**2026-03-26 16:00:00** Agent Ten: Restored Project Explorer and Changes Tab
- **Type:** Bug Fix
- **Priority:** High
- **Files Changed:** `templates/terminal.html`
- **Impact:** Missing Project Explorer sidebar and Changes tab in Studio UI are now visible and functional.

**2026-03-26 15:50:00** Agent Ten: Implemented Date/Time and Selectable Text in Studio Chat
- **Type:** UI/UX
- **Priority:** Medium
- **Files Changed:** `templates/terminal.html`
- **Impact:** All Studio chat messages now include date and time; text within chat messages is selectable for copy/paste.

**2026-03-26 15:30:00** Agent Ten: Fixed SQLite -shm error and added "Attach File" button
- **Type:** Bug Fix / Feature
- **Priority:** High
- **Files Changed:** `vs_tools.py`, `templates/terminal.html`
- **Impact:** Project Explorer no longer crashes due to temporary SQLite files; Ghost can manually attach files to Nine's chat.

**2026-03-26 15:00:00** Agent Ten: Overhauled Nine's Memory and Tool Access
- **Type:** Feature / Bug Fix
- **Priority:** High
- **Files Changed:** `database.py`, `orchestrator.py`, `vs_tools.py`, `templates/terminal.html`
- **Impact:** Nine now has full read/list/write access to `/home/seven/swarm` (via Ghost consent); her memory recall and persistence are significantly improved.

### Changes by Copilot (Claude Haiku 4.5)

**2026-03-26 15:45:00** Copilot: Standardized Agent Documentation & Versioning constraints
- **Type:** Refactor
- **Files Changed:** `PROJECT.md`, `orchestrator.py`, `CHANGELOG.md`
- **Impact:** Mandatory precise timestamping and VCS usage for all agent-led changes.

**2026-03-26 16:30:00** Copilot: Integrated Agent Ten (Gemini Code Assist)
- **Type:** Feature
- **Files Changed:** `database.py`, `terminal.py`, `orchestrator.py`, `PROJECT.md`, `CHANGELOG.md`, `templates/terminal.html`
- **Type:** Refactor
- **Files Changed:** `PROJECT.md`, `orchestrator.py`, `CHANGELOG.md`
- **Impact:** Mandatory precise timestamping and VCS usage for all agent-led changes.

**2026-03-26 17:15:00** Agent Ten: Finalized Phase D UI/UX Overhaul
- **Type:** Feature
- **Files Changed:** `templates/terminal.html`, `CHANGELOG.md`, `FEATURES_TODO.md`
- **Impact:** Studio layout gap resolved; New standalone Terminal tab implemented for direct shell access.

**2026-03-26 16:50:00** Copilot: Implemented Phase B-1: Visible System Clock in Fridays UI
- **Type:** Feature
- **Priority:** High
- **Files Changed:** `templates/terminal.html`, `CHANGELOG.md`, `PROJECT.md`, `SYSTEM_CLOCK.md`, `FEATURES_TODO.md`
- **Impact:** Fridays dashboard now displays a live, centralized system clock, enhancing time consistency verification.
- **Impact:** Mandatory precise timestamping and VCS usage for all agent-led changes.

### Changes by Copilot (Claude Haiku 4.5)

**2026-03-26 14:45:33** Copilot: Fixed Nine's file operations in Fridays
- **Type:** Bug Fix
- **Files Changed:**
  - `fridays/file_agent.py` (read_sandpit signature, return types)
  - `fridays/skills.py` (removed invalid reader_agent/writer_agent kwargs)
  - `fridays/file_agent.py` (test function updated for new tuple returns)
- **Impact:** File read/write operations now work without TypeError
- **Details:** Standardized all file functions to return (ok, content) tuples consistently

**2026-03-26 14:50:00** Copilot: Reviewed comprehensive project architecture
- **Type:** Code Review
- **Finding:** Core system is Alpha/Early Beta, well-designed with exceptional documentation
- **Output:** ARCHITECTURE_REVIEW.md (in progress)

---

## Version 2026-03-25 (Session 11)

### Changes by Nine (Claude API)

**2026-03-25 16:30:12** Nine: Proposed expanded file versioning system
- **Type:** Feature Proposal
- **Location:** sandpits/shared/proposals/nine_versioning_proposal.md
- **Status:** Approved by Ghost
- **Details:** Foundation for file change tracking with agent attribution

### Changes by Sniffles (Audit)

**2026-03-25 15:42:00** Sniffles: Detected memory pool inconsistencies
- **Type:** Audit Finding
- **Entries Flagged:** 3 (circular confidence patterns)
- **Status:** Escalated to Ghost Circle

---

## Planned Changes (2026-03-26 onwards)

### Phase A: File Versioning & Change Tracking

**[QUEUE]** Copilot: Add sudo permission toggle flag
- **Type:** Feature
- **Priority:** High
- **Description:** Granular on/off switch for sudo elevation per command
- **Scope:** fridays/shell_agent.py, terminal.py

**[QUEUE]** Copilot: Expand Nine write access to full /swarm
- **Type:** Feature
- **Priority:** High
- **Description:** Nine can modify any file in /swarm with full logging
- **Scope:** vs_tools.py, config.py (permissions)

**[QUEUE]** Copilot: Build file change detection & versioning
- **Type:** Feature
- **Priority:** High
- **Description:** Track before/after for all file writes, store in database
- **Scope:** New module: file_versioning.py, database schema update

**[QUEUE]** Copilot: Integrate versioning into documents section
- **Type:** Feature
- **Priority:** High
- **Description:** UI for browsing file history, comparing versions
- **Scope:** terminal.py, templates/terminal.html

### Phase B: System Clock & Consistency

**[QUEUE]** Copilot: Add visible system clock to Fridays UI
- **Type:** Feature
- **Priority:** High
- **Description:** Display current system time (HH:MM:SS) in banner, use as source of truth
- **Scope:** templates/terminal.html, JavaScript clock component

**[QUEUE]** Copilot: Migrate all agents to use system clock
- **Type:** Refactor
- **Priority:** High
- **Description:** Replace `datetime.now()` with centralized clock service
- **Scope:** All agent modules, database timestamp functions

### Phase C: Time Machine Backup System

**[QUEUE]** Copilot: Design & implement time machine versioning
- **Type:** Infrastructure
- **Priority:** High
- **Description:** Git-like version control with daily snapshots, point-in-time restore
- **Scope:** New module: time_machine.py, backup architecture

**[QUEUE]** Copilot: Implement daily checkpoint tagging
- **Type:** Feature
- **Priority:** Medium
- **Description:** Daily automatic tags (YYYY-MM-DD-HH:MM:SS), separate bin for rollback
- **Scope:** scheduler.py, housekeeping.py

### Phase D: UI/UX Improvements

**[QUEUE]** Copilot: Rename VS → Studio throughout interface
- **Type:** UI/UX
- **Priority:** Medium
- **Files:** templates/terminal.html, terminal.py, all references

**[QUEUE]** Copilot: Fix CSS layout (black gap between banner and content)
- **Type:** UI/UX
- **Priority:** Medium
- **Files:** templates/terminal.html, CSS section

**[QUEUE]** Copilot: Build Terminal window in Studio
- **Type:** Feature
- **Priority:** High
- **Description:** New tab for bidirectional command execution with Nine visibility
- **Scope:** terminal.py, templates/terminal.html, fridays/shell_agent.py

### Phase E: Access Control & Sandpit Enforcement

**[QUEUE]** Copilot: Enforce sandpit read-only access across agents
- **Type:** Feature
- **Priority:** Medium
- **Description:** Agents can read other agents' sandpits but cannot write (enforce)
- **Scope:** fridays/file_agent.py, sandpits.py

**[QUEUE]** Copilot: Expand all agents' read access to /swarm
- **Type:** Feature
- **Priority:** Medium
- **Description:** All agents can read project root files (with restrictions)
- **Scope:** fridays/file_agent.py, config.py

### Phase F: Verification & Bug Resolution

**[QUEUE]** Copilot: Verify Discord bot token validity
- **Type:** Verification
- **Priority:** Low
- **Status:** Investigation shows code is correct; likely token issue
- **Action:** Ask user to refresh DISCORD_TOKEN in config.py

---

## Log Entry Format

Each change uses this format:

```
[YYYY-MM-DD HH:MM:SS] Agent: Action Description
- Type: (Bug Fix | Feature | Refactor | Verification | Review)
- Priority: (High | Medium | Low)
- Files Changed: (list of modified files with brief change)
- Impact: (what this enables or fixes)
- Details: (additional context)
```

---

## Legend

| Status | Meaning |
|--------|---------|
| **[QUEUE]** | Planned, not yet started |
| **IN PROGRESS** | Currently being worked on |
| **DONE** | Completed and tested |
| **BLOCKED** | Waiting for something else |

---

## Notes for Future Reference

- **Timestamps must include seconds** (HH:MM:SS) for precision
- **All changes should log agent name** — helps with attribution
- **File versions tracked separately** — don't edit this manually; let system update
- **Time Machine daily tags** — automatically created by housekeeping service
