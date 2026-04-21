# Developer Guide — Seven's Swarm

**Last Updated:** 2026-04-20 | **Consolidates:** ALM_COOKBOOK, ALM_DRIVER, DEPLOYMENT_GUIDE, DEVELOPER_WORKFLOW, ENVIRONMENTS_REFERENCE, MULTI_STAGE_WORKFLOW, UAT_TEST_SCRIPTS, VERSION_CONTROL

---

## Core Principles

1. **All changes go through proposals** — Ghost approves, Duck reviews, agents execute
2. **Multi-stage environments** — DEV (5051) → UAT (5053) → PROD (5050)
3. **Complete traceability** — every change logged, every agent action audited, full version history

---

## ALM Workflow

### Phase 1 — Propose

By Ghost or any agent in the Fridays chat:

```
SKILL alm_create_proposal
  title: "Add new memory pool for Agent X"
  description: "Extends memory tables to support Agent X with importance thresholds"
  impact: "Agent X can now persist domain-specific knowledge"
  files: ["database.py", "orchestrator.py"]
```

Result: `work_proposals` entry created (status: `pending`), proposal ID assigned (e.g., `INTERNAL-TERMINAL_UI-0150`).

### Phase 2 — Duck Review (Automated, 1–3s)

```
Duck checks:
  Title length > 5 chars
  Description > 20 chars
  At least one file listed
  No contradictions with policy
→ APPROVED: status → approved, duck_verdict logged
→ REJECTED: feedback posted to chat, status stays pending
```

Weak proposals rejected: "Fix things" (too vague), no description, empty file list.

### Phase 3 — Ghost Approve

Studio → Work Proposals → find proposal → click Approve.
Chat receives: "✓ Approved. Run `SKILL alm_self_approve <id>` to begin."

### Phase 4 — Execute

```bash
SKILL alm_self_approve INTERNAL-TERMINAL_UI-0150
# status → in_progress

SKILL fs_patch_lines database.py 45 62
<<<NEW>>>
replacement content

SKILL alm_complete INTERNAL-TERMINAL_UI-0150
# status → done → triggers Duck quality check
```

### Phase 5 — Duck Quality Gate (Automated)

Duck runs quality check on the completed proposal. PASS → status → `uat`. FAIL → status → `in_progress` with feedback posted to chat. Agent must fix and re-run `SKILL alm_complete`.

### Phase 6 — Mark Executed (Ghost)

Studio → Work Proposals → UAT tab → Mark Executed → status → `executed` → live on PROD.

### Proposal Status Flow

```
pending → approved → in_progress → done → uat → executed
```

---

## Environments

### DEV — Port 5051

Purpose: agent development, quick validation
Database: `swarm_memory_dev.db`
Access: Ghost + Nine only

```bash
cd /home/seven/swarm
SWARM_ENV=dev python3 frontend/terminal.py
```

### UAT — Port 5053

Purpose: staged testing before production
Database: `swarm_memory_uat.db`

```bash
SWARM_ENV=uat python3 frontend/terminal.py
```

### PROD — Port 5050

Purpose: live production
Database: `swarm_memory.db` (canonical)
Service: `swarm-terminal-prod.service` (systemd)

```bash
sudo systemctl start swarm-terminal-prod
sudo systemctl status swarm-terminal-prod
journalctl -u swarm-terminal-prod -f
```

---

## Git Workflow

### Branch Structure

```
main         — Production-ready, never directly committed
develop      — Integration branch
proposal/*   — Feature branches for proposals
```

Current branch: `proposal/GHOST_CODER-0890`

### Commit Standard

Every commit must include:
1. Agent attribution
2. Timestamp (YYYY-MM-DD HH:MM:SS)
3. One-line reason
4. Linked proposal ID

```bash
git commit -m "Fix: FL-001 routing gate missing Qwen3.6

Agent: Nine (Claude Sonnet 4.6)
Timestamp: 2026-04-20 14:35:22 UTC
Proposal: INTERNAL-TERMINAL_UI-0156
Files: orchestrator.py (1 line)
Impact: Qwen3.6 now properly routed to large model pipeline"
```

### Pull Request Template

```markdown
## Proposal
INTERNAL-TERMINAL_UI-0156

## Summary
- What changed and why
- Risk level (low/medium/high)

## ALM Status
- Duck verdict: PASS
- Files changed: N
- DB schema changes: yes/no

## Testing
- [ ] DEV tested
- [ ] UAT regression passed
- [ ] Memory pool regressions: none
- [ ] Sandpit enforcement holds

## Rollback
git revert <commit>

## Agent
Nine (Claude Sonnet 4.6)
```

---

## File Versioning

Every file write is tracked with before/after content in `file_versions` table.

```python
from file_versioning import track_file_change
track_file_change(
    filepath="/home/seven/swarm/orchestrator.py",
    old_content=previous_content,
    new_content=new_content,
    agent="Nine",
    reason="Fixed FL-001 routing gate for Qwen3.6"
)
```

Query history:
```bash
SKILL history_show orchestrator.py
```

Restore previous version:
```bash
SKILL history_restore orchestrator.py --to-version 5
```

---

## Database Backup & Checkpoints

**Daily checkpoint (automatic at 02:00 UTC via scheduler):**
- DECISION-{YYYY-MM-DD} created in `decisions` table
- `time_machine.daily_checkpoint` record created
- State logged to `sandpits/twelve/logs/`

**Manual checkpoint:**
```bash
SKILL time_snapshot "manual checkpoint before major refactor"
```

**Point-in-time restore:**
```bash
SKILL time_restore --to-date 2026-04-15 23:59:00
```

---

## UAT Checklist

**Functionality (30 min):**
- [ ] Chat with all local agents responds correctly
- [ ] Web search (DuckDuckGo, Tavily) returns results
- [ ] Debate triggers correctly on disagreement
- [ ] Duck sanity check runs post-ticket (every ticket)
- [ ] Email pipeline: send → process → reply (full round-trip)
- [ ] Telegram pipeline: send → process → reply
- [ ] Discord pipeline: DM → process → reply

**Data Integrity (15 min):**
- [ ] No memory pool regressions
- [ ] Importance thresholds respected (agents see only importance 3+)
- [ ] Archived memories not returned in queries
- [ ] Sandpit writes logged to `sandpit_log`
- [ ] File versions tracked with content_before/after

**Audit Trail (10 min):**
- [ ] Duck verdicts logged with reason
- [ ] Sniffles audits unarchived entries on queue quiet
- [ ] File versioning tracked all changes in session
- [ ] `activity_log` shows all agent actions
- [ ] Ghost Circle shows Duck checks + Claude calls

**ALM Workflow (15 min):**
- [ ] Create proposal → Duck reviews → status: approved
- [ ] Agent executes (SKILL alm_self_approve) → status: in_progress
- [ ] Agent completes (SKILL alm_complete) → Duck quality check → status: uat
- [ ] Ghost marks executed → status: executed, PROD updated

---

## Emergency Procedures

### System Unresponsive

```bash
pkill -f "frontend/terminal.py"
free -h
curl http://localhost:11434/api/ps     # check Ollama
systemctl restart ollama               # restart Ollama if stuck
sudo systemctl restart swarm-terminal-prod
```

### Queue Stuck

```bash
# Check queue state in Fridays Terminal or:
sqlite3 swarm_memory.db "SELECT id, status, created_at FROM queue WHERE status='processing';"

# Mark stuck entries abandoned:
sqlite3 swarm_memory.db "UPDATE queue SET status='abandoned' WHERE created_at < datetime('now', '-2 hours') AND status='processing';"

sudo systemctl restart swarm-listener
```

### Database Corruption

```bash
cp swarm_memory.db swarm_memory.db.BROKEN
SKILL time_restore --to-date 2026-04-19 02:00:00
```

### Model Won't Unload

```bash
curl http://localhost:11434/api/ps                    # list loaded models
curl -X POST http://localhost:11434/api/generate \    # force unload
  -d '{"model":"gemma3:latest","keep_alive":0}'
```

---

## Deployment Checklist

Before shipping a major change to PROD:

1. Code review (Nine + Ten)
2. Syntax check: `python3 -m py_compile *.py`
3. Import check (no circular dependencies)
4. Database schema migration tested on DEV
5. DEV tested (feature works)
6. UAT tested (no regressions — full checklist above)
7. Rollback plan documented
8. Proposal status: `executed`
9. PROD deployment window scheduled
10. Ghost notified via Discord

---

## Agent SKILL Reference

### Filesystem (Read-only)

```
SKILL fs_readonly read <path>
SKILL fs_readonly lines <path> <start> <end>
SKILL fs_readonly grep <path> <pattern>
SKILL fs_readonly ls <directory>
```

### Filesystem (Write — ALM-gated)

```
SKILL fs_patch_lines <path> <start> <end>
<<<NEW>>>
replacement content

SKILL fs_write <path> <content>
```

### ALM

```
SKILL alm_create_proposal "Title" "Description"
SKILL alm_self_approve <id>
SKILL alm_vortex before-<label>
SKILL alm_complete <id>
```

### System

```
SKILL shell <command>            (Level 4+, whitelist only)
SKILL history_show <path>
SKILL history_restore <path> --to-version N
SKILL time_snapshot "reason"
SKILL queue_status
SKILL db_check
```

### Library

```
SKILL shell curl -s 'http://localhost:5050/api/library/search?q=<keyword>'
SKILL shell curl -s -X POST http://localhost:5050/api/library/ingest \
  -H 'Content-Type: application/json' \
  -d '{"type":"text","title":"...","content":"...","tags":["..."],"added_by":"agent_name"}'
```

---

## Windows Development (Dual-Boot)

The OptiPlex dual-boots Linux/Windows. Models are on the shared NTFS partition (`/mnt/ollama-models` in Linux, assigned a drive letter in Windows).

**Windows app entrypoint:** `windows/launcher.py`
**Build:** `windows/build.bat` → `dist/Fridays/Fridays.exe`
**Requirements:** `windows/requirements-windows.txt`

The launcher:
1. Detects frozen (PyInstaller) vs source mode
2. Sets `SWARM_ROOT` to persistent data directory
3. Creates DB and sandpits on first launch
4. Starts Flask in a background thread
5. Opens native Edge WebView2 window (pywebview)
6. Shows system tray icon (pystray)

Linux-specific features (systemctl, tailscale, sudo) fail gracefully — Flask blueprint loader already handles this with per-blueprint error isolation.
