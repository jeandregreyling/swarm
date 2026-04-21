# FEATURES_TODO.md — Planned Features & Implementation Queue

<!-- markdownlint-disable -->

_Comprehensive list of all planned features, organized by phase and priority._
_Last updated: 2026-04-19 by Copilot (Session 21)_

---

## Executive Summary

**30 tasks** across 9 phases. Estimated timeline: **6-10 weeks** to full implementation.

| Phase | Name | Priority | Est. Size | Status |
| ----- | ---- | -------- | --------- | ------ |
| **A** | File Versioning & Change Tracking | 🔴 High | 4 weeks | DONE |
| **B** | System Clock & Time Consistency | 🔴 High | 1 week | DONE |
| **C** | Time Machine Backup System | 🔴 High | 2 weeks | Queued |
| **D** | UI/UX Improvements | 🟡 Medium | 1 week | DONE |
| **E** | Access Control & Sandpits | 🟡 Medium | 1 week | Queued |
| **F** | Verification & Bug Resolution | 🟢 Low | 2 days | Queued |
| **G** | Frontend Tile Modularisation | 🔴 High | 3 weeks | In Progress |
| **H** | Desktop Application Path | 🟡 Medium | 4 weeks | Planned |
| **I** | Atmosphere Engine | 🔴 High | 2-3 weeks | Planned |
| **J** | Enhanced Tasker & RAG Automation | 🔴 High | 1 week | **DONE (Session 21)** |

---

## Phase J: Enhanced Tasker & RAG Automation (Session 21 — DONE)

### J-1: Python Task Runner ✅
- Built `fridays/task_runner.py` — decorator-based task registry with 13 built-in tasks
- Categories: housekeeping, knowledge, monitoring, reporting
- Execution logged to `task_run_log` DB table

### J-2: Scheduler Security + PYTHON Dispatch ✅
- Fixed shell injection vector (`shell=True` → `shlex.split()`) in `fridays/scheduler.py`
- Added PYTHON action type — calls task_runner instead of subprocess
- Extended schedule support: weekly, monthly, hourly, interval
- Removed hardcoded `run_daily_digest()` from main loop

### J-3: Tasker REST API + UI ✅
- Full CRUD API in `frontend/blueprints/tasker_bp.py`
- Bootstrap endpoint seeds 7 default tasks
- PYTHON type in UI filter/form, preset buttons, bootstrap button

### J-4: Fridays Knowledge RAG Seeding ✅
- Extended `lib/knowledge/seed.py` with `fridays` collection
- 17 swarm docs mapped to 4 subcategories (~348K chars)
- Available via `POST /api/library/seed {"collection": "fridays"}`

### J-5: Agent Tasker Awareness ✅
- Added 3 new skills to `fridays/skills.py`: tasker_list, tasker_run, tasker_history
- Agents can now view, trigger, and inspect scheduled tasks

### J-6: Seven LLM Memory Fix ✅
- Root cause: 3 models loaded with `keep_alive=-1` → 13.5GB swap thrash
- Fixed: `keep_alive=300`, unloaded idle models

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

---

## Phase I: Atmosphere Engine (HIGH PRIORITY)

### I-1: Replace Fixed Theme Presets with Atmosphere Model

**Description:** Retire the current named-theme UX and replace it with a single continuous Atmosphere control.

**Why:** The current theme set is visually inconsistent and feels like unrelated skins. Fridays should feel like one living environment that shifts across the day.

**Product naming rule:**
- [ ] User-facing language says `Atmosphere`
- [ ] Internal compatibility may keep `theme` naming in code/storage during migration
- [ ] Do not create a separate "Atmosphere system" beside the old theme system; this is the replacement path

**Implementation:**
- [ ] Remove named preset themes from the main settings UI
- [ ] Add one continuous morning → night Atmosphere slider
- [ ] Blend colors across the day instead of snapping between fixed palettes
- [ ] Preserve current manual override behavior until changed back to default

**Files to Update:**
- `frontend/static/js/core/theme.js`
- `frontend/static/css/themes.css`
- `frontend/static/css/components.css`
- `frontend/templates/terminal_base.html`
- `frontend/themes/fridays.json`

**Acceptance Criteria:**
- [ ] No fixed-preset theme buttons remain in the main settings flow
- [ ] Slider updates visuals smoothly with no hard jumps
- [ ] Manual override persists using the current settings model

### I-2: Atmosphere Follows One Selected Clock Location

**Description:** Use one selected world clock as the source of truth for Atmosphere timing.

**Why:** Fridays should be able to "feel like" another place in the world, not only the host machine timezone.

**Implementation:**
- [ ] Expose the selected clock/location in the Atmosphere settings panel
- [ ] Read from the existing home-page world clock selection
- [ ] Default Atmosphere position from the chosen location's local time
- [ ] Keep manual slider override available

**Acceptance Criteria:**
- [ ] User can choose which saved clock drives Atmosphere
- [ ] Auto/default mode follows that location's local time
- [ ] Manual override still works and persists

### I-3: Expand to All Saved Front-Page Clocks

**Description:** Bring the saved clock list into the Atmosphere screen so the selected location is obvious and editable.

**Implementation:**
- [ ] Show the current saved clocks in Atmosphere settings
- [ ] Make location selection use those saved clocks, not a separate duplicated list
- [ ] Keep the current 5-clock model in sync between home and Atmosphere

**Acceptance Criteria:**
- [ ] Atmosphere screen shows the same saved locations as the front page
- [ ] Changing saved clocks is reflected in Atmosphere selection

### I-4: Add Weather Modifiers Behind the Atmosphere Slider

**Description:** Weather becomes a modifier layer on top of the same Atmosphere timeline.

**Why:** "Cloudy and cold London at 8AM" should feel different from "clear and warm Melbourne at 8AM" without becoming a separate theme preset system again.

**Implementation:**
- [ ] Add weather metadata to each saved clock/location
- [ ] Support modifier families like cloudy, rainy, hot, cold, clear
- [ ] Apply weather as palette adjustments behind the same time slider
- [ ] Keep one coherent Atmosphere model rather than time theme + weather theme stacking

**Dependencies:**
- [ ] Clock weather lookup/API design
- [ ] Location-weather refresh schedule

**Acceptance Criteria:**
- [ ] Atmosphere can reflect both time of day and weather state
- [ ] Weather effects are additive modifiers, not unrelated preset swaps

### I-5: Favorites and Saved Atmospheres (Later)

**Description:** Allow one or more favorite saved looks per clock/location after the base system is stable.

**Why:** Users will discover combinations they like, but this should not be designed before the core Atmosphere model feels right.

**Implementation:**
- [ ] Design favorite save model only after I-1 through I-4 feel stable
- [ ] Consider one favorite per clock first before broader preset storage

**Acceptance Criteria:**
- [ ] Deferred until the main Atmosphere engine is stable and liked in daily use
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

---

## Phase G: Frontend Tile Modularisation (HIGH PRIORITY)

*Decided: 2026-04-04. See ARCHITECTURE.md — Frontend Evolution section for full design.*

The current monolith (`terminal.py` ~16k lines + `terminal_base.html` ~16.5k lines) is being split tile-by-tile into self-contained Flask Blueprints + ES module HTML/JS fragments. Each tile is reviewed and cleaned before extraction. No tile is extracted until it passes review.

**Why:** A bad edit to one tile currently risks crashing the whole server. Isolation = safety.

### G-1: Chat Tile — Review & Hardening

**Status:** DONE (2026-04-04)

**What was done:**
- [x] Full code review completed — 5 issues identified
- [x] BUG: Chat job state lost on server restart → `chat_jobs` DB table + startup orphan cleanup
- [x] BUG: 10 functions nested inside `api_chat()` → extracted to module level via AST script
- [x] BUG: Duplicate `_extract_skill_lines` → removed inner copy, unified to `_extract_skill_lines_from_text`
- [x] BUG: False-positive proposal auto-creation → gate requires colon-form field labels
- [x] BUG: Per-request `ThreadPoolExecutor` churn + deadlock risk → two named module-level pools
- [ ] Extract to `tiles/chat/routes.py` (pending modularisation pass)

---

### G-2: Terminal Tile — Review & Hardening

**Status:** In Progress (2026-04-04)

**What was found:**
- Shortcut system incomplete — no edit, no reorder, no delete for defaults, `prompt()` dialogs only
- Sudo safe list (`_SUDO_ALLOWED`) hardcoded regex — no UI or API to manage it
- `addTerminalShortcut()` has a copy-paste variable name error (`chatWin` instead of `termWin`) — works but misleading

**Pending fixes:**
- [ ] Shortcut manager modal — edit/delete for all shortcuts (default + custom), drag-to-reorder, unified localStorage storage
- [ ] Sudo allowlist — `sudo_allowlist` DB table, 3 API endpoints (GET/POST/DELETE), frontend panel
- [ ] Extract to `tiles/terminal_tile/routes.py` (after fixes)

---

### G-3: Files Tile — Review & Hardening

**Status:** Not started

- [ ] Full code review (same depth as Chat + Terminal reviews)
- [ ] Document issues
- [ ] Fix identified bugs
- [ ] Extract to `tiles/files/routes.py`

---

### G-4: ALM/Studio Tile — Review & Hardening

**Status:** Not started

- [ ] Full code review
- [ ] Document issues
- [ ] Fix identified bugs
- [ ] Extract to `tiles/alm/routes.py`

---

### G-5: Monitor Tile — Review & Hardening

**Status:** Not started

- [ ] Full code review
- [ ] Document issues
- [ ] Fix identified bugs
- [ ] Extract to `tiles/monitor/routes.py`

---

### G-6: Vortex Tile — Review & Hardening

**Status:** Not started

- [ ] Full code review (Vortex not fully linked — link as part of this pass)
- [ ] Document issues
- [ ] Fix identified bugs
- [ ] Extract to `tiles/vortex/routes.py`

---

### G-7: Base Layer Extraction

**Status:** Blocked on G-1 through G-6

- [ ] Reduce `terminal.py` to: startup, auth, ALM gate, blueprint auto-registration
- [ ] Reduce `terminal_base.html` to: shell layout, shared JS utilities, tile injection loader
- [ ] Validate all tiles load correctly via fragment injection

---

## Phase H: Desktop Application Path (MEDIUM PRIORITY)

*Decided: 2026-04-04. Prerequisite: Phase G complete.*

Target: standalone desktop app via Electron or Tauri. Flask runs as a bundled local subprocess. Frontend becomes a packaged web app. No backend rewrite required.

### H-1: Electron Prototype

**Status:** Planned (post Phase G)

- [ ] Evaluate Electron vs Tauri — decide based on team familiarity and bundle size
- [ ] Wrap Flask server as child process in Electron main process
- [ ] Point Electron webview at `localhost:5050`
- [ ] Test all tile functions work inside webview
- [ ] Basic window chrome (title bar, system tray icon)

**Files to create:**
- `desktop/main.js` — Electron main process
- `desktop/package.json` — Electron app manifest
- `desktop/preload.js` — IPC bridge if needed

---

### H-2: App Packaging & Distribution

**Status:** Planned (post H-1)

- [ ] Configure electron-builder or Tauri CLI for Linux (.deb / AppImage)
- [ ] Bundle Flask + Python runtime (or document dependency install)
- [ ] Bundle SQLite database at first run
- [ ] Auto-update mechanism (optional)
- [ ] System tray: show/hide, quit

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
