# VERSION_CONTROL.md — Time Machine & File Versioning Strategy

_Seven's Swarm comprehensive version control and backup system._
_Last updated: 2026-03-26 by Ten (GPT)_

---

## Overview

Seven's Swarm uses **true version control** (not snapshots) combined with **daily timestamp tagging** to enable point-in-time restoration. The system tracks:

1. **File changes** — every edit with before/after content
2. **Database changes** — versioned rows with commit metadata
3. **Daily checkpoints** — automated tags for restore points
4. **Change attribution** — agent name, timestamp, reason for every change

---

## Architecture

### Layer 1: Change Tracking (Real-time)

Every file write and database update is logged:

```
FILE CHANGES:
  swarm_memory.db → file_versions table
  ├── file_path (e.g., "/home/seven/swarm/config.py")
  ├── agent (e.g., "Nine", "Ten (GPT)", "Sniffles")
  ├── timestamp (e.g., "2026-03-26 14:45:33")
  ├── action (e.g., "write", "delete", "rename")
  ├── content_before (full previous content)
  ├── content_after (full new content)
  ├── commit_hash (SHA256 of this version)
  └── tag (e.g., "checkpoint-2026-03-26T00:00:00Z")

DATABASE CHANGES:
  swarm_memory.db → audit_log table
  ├── timestamp
  ├── agent
  ├── table_name (e.g., "memory_pools", "tickets")
  ├── operation (INSERT, UPDATE, DELETE)
  ├── row_id
  └── before_json / after_json (full row snapshots)
```

### Layer 2: Daily Checkpoints

A daily background job creates temporal tags:

```
Time Machine Snapshots:
  ├── 2026-03-25T00:00:00Z (daily 00:00 UTC)
  │   └── Pointers to valid file versions at that moment
  │
  ├── 2026-03-26T00:00:00Z
  │   └── "What was the state on March 26 at midnight?"
  │
  └── 2026-03-27T00:00:00Z
```

These are **not duplicates** — just pointers + metadata. The actual versioned content lives in the database and original files.

### Layer 3: Rollback Bin

When you request restore to a specific date:

```
Restore Request: "Go back to 2026-03-24"

System Action:
  1. Identify all changes AFTER 2026-03-24T00:00:00Z
  2. Move newer versions to: /home/seven/swarm/.timemachine/bin/2026-03-26_restore/
     ├── config.py.v2026-03-26-14-45-33 (moved here for safety)
     ├── database_audit_log.2026-03-26-14-46-00 (for review)
     └── MANIFEST.md (what was deleted/reverted)
  3. Restore all files to 2026-03-24T23:59:59Z state
  4. User can review bin, restore specific items if needed
```

---

## Detailed Schema

### file_versions Table (NEW)

```sql
CREATE TABLE file_versions (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,           -- Full path to file
    agent TEXT NOT NULL,               -- Who changed it (Nine, Ten (GPT), etc.)
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,  -- When changed (with seconds)
    action TEXT,                       -- write, delete, rename
    content_before TEXT,               -- Previous full content
    content_after TEXT,                -- New full content
    size_bytes INTEGER,                -- Size of content_after
    reason TEXT,                       -- Why (e.g., "Fixed bug BUG-003")
    commit_hash TEXT,                  -- SHA256(timestamp + file_path + content_after)
    checkpoint_tag TEXT,               -- Daily tag if part of checkpoint
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path, timestamp)       -- No duplicate timestamps for same file
);

-- Indexes for fast lookups
CREATE INDEX idx_file_versions_file_path ON file_versions(file_path);
CREATE INDEX idx_file_versions_timestamp ON file_versions(timestamp);
CREATE INDEX idx_file_versions_agent ON file_versions(agent);
CREATE INDEX idx_file_versions_checkpoint ON file_versions(checkpoint_tag);
```

### audit_log Table (EXTEND)

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    table_name TEXT,                   -- Which table was modified
    operation TEXT,                    -- INSERT, UPDATE, DELETE
    row_id INTEGER,
    before_json TEXT,                  -- Full JSON of previous state
    after_json TEXT,                   -- Full JSON of new state
    reason TEXT,                       -- Why the change
    checkpoint_tag TEXT,               -- Daily tag
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### daily_checkpoints Table (NEW)

```sql
CREATE TABLE daily_checkpoints (
    id INTEGER PRIMARY KEY,
    checkpoint_date DATE NOT NULL,     -- YYYY-MM-DD
    checkpoint_timestamp DATETIME,     -- Full timestamp (2026-03-26T00:00:00Z)
    tag TEXT UNIQUE,                   -- "checkpoint-2026-03-26"
    files_included INTEGER,            -- Count of known files at this point
    db_rows_included INTEGER,          -- Approximate row count in audit_log
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT                        -- 'valid', 'partial', 'restored'
);
```

---

## Workflow: File Change Tracking

### When Nine Writes a File

```python
# 1. Nine.write_file("/home/seven/swarm/config.py", new_content)
#    ↓
# 2. file_versioning.track_write()
#    ├── Read current file (content_before)
#    ├── Compare: is_actual_change?
#    ├── If yes:
#    │   ├── Compute commit_hash = SHA256(timestamp + path + new_content)
#    │   ├── Insert INTO file_versions (...)
#    │   ├── Write new file to disk
#    │   └── Log to ghost_circle: "Nine wrote config.py (reason: ...)"
#    └── If no: skip (prevent pointless duplicates)
```

### When Agent Changes Database

```python
# 1. Agent updates a memory pool entry
#    ↓
# 2. database.py: execute("UPDATE memory_gemma SET ... WHERE id=?")
#    ├── Before: snapshot the row to JSON
#    ├── Execute UPDATE
#    ├── After: snapshot the modified row
#    ├── INSERT INTO audit_log (before_json, after_json, ...)
#    └── Log agent + reason
```

---

## Workflow: Daily Checkpointing

**Trigger:** Daily at 00:30 UTC (after housekeeping runs)

```python
# time_machine.create_daily_checkpoint()
#
# 1. Query all file_versions from past 24 hours
# 2. Tag them: checkpoint_tag = "checkpoint-2026-03-26"
# 3. Compute manifest: which files were in /swarm at 00:00:00Z?
# 4. Create daily_checkpoints row
# 5. Log to ghost_circle (for review)
```

---

## Workflow: Restore to Point-in-Time

**Command:** `SKILL restore_to_date 2026-03-24`

```python
# time_machine.restore_to_date("2026-03-24")
#
# 1. Find checkpoint for 2026-03-24T23:59:59Z
# 2. Identify all changes AFTER that moment
# 3. Create bin:
#    mkdir -p /home/seven/swarm/.timemachine/bin/2026-03-26_RESTORE/
#    
# 4. For each newer file:
#    ├── Find its last version before 2026-03-25T00:00:00Z
#    ├── Restore content from file_versions table
#    ├── If file was created AFTER 2026-03-24:
#    │   └── Move to bin/ (don't restore, just archive)
#    └── If file existed then:
#        └── Restore to pre-2026-03-25 state
#
# 5. For database:
#    ├── Identify audit_log rows after checkpoint
#    ├── Compute rollback: revert INSERT→DELETE, UPDATE→restore old values
#    ├── Move rolled-back data to bin/ for review
#    └── Execute reversals
#
# 6. Create manifest:
#    /home/seven/swarm/.timemachine/bin/2026-03-26_RESTORE/MANIFEST.md
#    ├── What was rolled back
#    ├── Files moved to bin
#    ├── Database rows affected
#    └── "Review these before committing rollback"
```

---

## Key Design Decisions

### 1. Why Not Just Git?

Git is designed for source code. We need:
- **Database versioning** (git can't help here)
- **Binary file changes** (SQLite, JSON)
- **Timestamp precision** (seconds matter for agent actions)
- **Agent attribution** (not just commit author)
- **Easy rollback UI** (not CLI)

**Decision:** Use database-backed versioning with Git-like concepts (commits, tags, diffs).

### 2. Why Store Full Content (not diffs)?

- Diffs are hard with complex documents
- Disk is cheap; computing diffs has cost
- Fast restore is more important than space optimization
- Readability: "show me what changed" is instant

**Tradeoff:** Database will grow. Mitigation: periodic archival of old versions to gzip files.

### 3. Why Daily Checkpoints, Not Hourly?

- Reduces tag explosion
- Balances restore granularity with bookkeeping overhead
- Aligns with human workflow ("go back to yesterday")
- Can still restore to specific minutes if needed (file_versions stores precise timestamp)

---

## System Clock Integration

**Critical:** All timestamps use centralized system clock.

```python
# OLD (BROKEN):
timestamp = datetime.now()  # Different on each machine
timestamp = time.time()     # Different timezone handling

# NEW (CORRECT):
from system_clock import get_system_time
timestamp = get_system_time()  # "2026-03-26 14:45:33 UTC"
```

The system clock is:
- ✅ Visible in Fridays UI (banner, always showing current time)
- ✅ Used by all agents
- ✅ Used by all database functions
- ✅ Synchronized with NTP (if online) or hardware RTC

---

## Restore Bin Structure

After user requests restore, files pending review live in a sandboxed bin:

```
/home/seven/swarm/.timemachine/
├── bin/
│   ├── 2026-03-26_RESTORE/              (today's restore request)
│   │   ├── config.py.v2026-03-26-14-45-33
│   │   ├── nine_memory.pool.v2026-03-26-14-46-00
│   │   ├── swarm_memory.db.audit_rollback.sql
│   │   └── MANIFEST.md
│   │
│   ├── 2026-03-25_RESTORE/              (previous restore)
│   └── ...
│
└── archive/                             (old versions, gzipped)
    ├── file_versions-2026-Q1.db.gz
    └── ...
```

User can:
1. Review MANIFEST.md
2. Restore all (commit the rollback)
3. Restore specific items from bin
4. Discard bin (reject rollback)

---

## Implementation Roadmap

### Week 1: Core Versioning
- [ ] Create file_versions table
- [ ] Create audit_log extension
- [ ] Build file_versioning.py module
- [ ] Integrate with file_agent.py and all database writes

### Week 2: Checkpoints & Time Machine
- [ ] Create daily_checkpoints table
- [ ] Build time_machine.py module
- [ ] Implement restore_to_date() function
- [ ] Create manage_bin() UI

### Week 3: UI & Integration
- [ ] Build "Version History" tab in Studio
- [ ] File diff viewer
- [ ] Restore request UI
- [ ] System clock in banner

### Week 4: Hardening
- [ ] Backup archival (old versions → gzip)
- [ ] Integrity checks (verify commit_hash)
- [ ] Performance tuning (large tables)
- [ ] Documentation + runbooks

---

## Notes

- **Concurrency:** When Nine and Sniffles write simultaneously, database UNIQUE constraint on (file_path, timestamp) ensures no duplicates
- **Rollback Safety:** Restore creates bin; nothing is permanent until user approves
- **Performance:** file_versions queries are indexed; even with millions of rows, lookups are O(log n)
- **Disk:** Count on ~1-5 MB per day of versioning metadata (varies with file change frequency)
