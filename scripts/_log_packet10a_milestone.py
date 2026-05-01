#!/usr/bin/env python3
"""Log PACKET-10A milestone via studio_milestone.log_milestone."""
import os
import sys
# S-7C7ED96F5B — resolve repo root relative to this file (override via SWARM_ROOT)
_SWARM_ROOT = os.environ.get(
    "SWARM_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)
from scripts.studio_milestone import log_milestone

story = """\
PACKET-10A: Backup & Trace Hardening — closed.

Why now: the user flagged that swarm_memory.db (857 MB) is the canonical
state and lives only on this SSD. If the disk dies, ~8.7k episodes, 5.4k
Vortex checkpoints, and the whole platinum ledger go with it.

What landed:
- scripts/backup_swarm.sh (driver) + scripts/backup_excludes.txt
- Three destinations live and verified end-to-end:
    local  ~/swarm-backups/                 → 883 MB tarball
    ntfs   /mnt/llm/swarm-backups/          → 883 MB tarball
    usb    /media/seven/462B-E832/swarm-backups/  → 883 MB tarball
- Hot-safe snapshot via `sqlite3 .backup` (no write-lock on live DB),
  PRAGMA integrity_check before tar, SHA256 sidecar, manifest JSON,
  retention=14 newest tarballs per target, audit log JSONL.
- scripts/backup_verify.py — recent-mode (used by self-test) and extract-mode
  (full restore drill: tar → DB → integrity_check → row sanity on
  seven_episodes / scheduled_tasks / time_checkpoints).
- scripts/vortex_restore.py — extracts time_checkpoints from any backup into
  a standalone SQLite file. User explicitly named Vortex as critical;
  restore path is now non-magical.
- scripts/backup_to_tablet.sh — manual Samsung tablet sync via gvfs/MTP
  (intentionally not scheduled — MTP is too unreliable for cron).
- fridays/task_runner.py — `swarm_backup` and `swarm_backup_verify` tasks
  registered.
- scheduled_tasks DB — daily 04:30 (backup all targets) + 05:30 (verify).
- scripts/architecture_self_test.py — invariant #17 added: last successful
  backup within 25h. Now 17/17 PASS.

Decisions:
- USB excludes file path was bug #1 — `swarm_memory.db` was anchored
  unanchored, so it excluded the snapshot too. Fixed by anchoring excludes
  with `./` prefix and routing the snapshot through `db-snapshot/` subdir.
- Not encrypted (per user: "dont need to be encrypted just make it safe
  enough"). Tarballs are plain gzip, readable from any OS.
- GitHub push is tier-2 (PACKET-09 work still uncommitted on
  proposal/GHOST_CODER-2128). Backup tarballs already protect that state, so
  the git error can be diagnosed separately without risking data loss.

Anomaly logged for follow-up (NOT this packet):
- Vortex stopped producing checkpoints at 2026-04-30 14:10:42. Both git
  vortex-* tags and time_checkpoints rows agree. ~31h gap. Backup captures
  the existing 5394 checkpoints, but Vortex itself needs revival.
"""

print(log_milestone(
    packet="PACKET-10A",
    title="Backup & Trace Hardening — closed",
    story=story,
    status="done",
))
