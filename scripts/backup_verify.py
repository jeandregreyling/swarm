#!/usr/bin/env python3
"""
scripts/backup_verify.py — PACKET-10A backup integrity gate.

Two modes:

  python3 scripts/backup_verify.py recent
    Reads runtime/backups/log.jsonl and checks the most recent successful
    backup is younger than RECENT_MAX_AGE_S (default: 25h). Used by the
    architecture self-test (invariant #17).

  python3 scripts/backup_verify.py extract [<archive_path>]
    Extracts the given tarball (or the latest local tarball if omitted) to a
    scratch dir, then runs PRAGMA integrity_check on the embedded DB snapshot
    plus a row-count sanity check. Refuses to mark success unless DB is clean.

Exit codes: 0 ok, 1 fail, 2 caller error.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(os.environ.get("SWARM_ROOT", "/home/seven/swarm"))
LOG_FILE = REPO / "runtime" / "backups" / "log.jsonl"
LOCAL_DEST = Path.home() / "swarm-backups"
RECENT_MAX_AGE_S = int(os.environ.get("SWARM_BACKUP_MAX_AGE_S", str(25 * 3600)))

# Tables we expect to see populated in any healthy backup.
SANITY_TABLES = [
    ("seven_episodes",      1),     # Seven brain has at least one episode
    ("scheduled_tasks",     1),     # Tasker has at least one task
    ("time_checkpoints",    1),     # Vortex has produced at least one checkpoint
]


def cmd_recent() -> int:
    if not LOG_FILE.exists():
        print(f"[verify:recent] FAIL — no log file at {LOG_FILE}")
        return 1

    last_ok_ts = 0.0
    last_ok_target = None
    last_ok_archive = None
    with LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("outcome") != "ok":
                continue
            ts_str = ev.get("ts") or ""
            try:
                # ISO8601 with timezone — convert to epoch.
                from datetime import datetime
                dt = datetime.fromisoformat(ts_str)
                ts = dt.timestamp()
            except Exception:
                continue
            if ts > last_ok_ts:
                last_ok_ts = ts
                last_ok_target = ev.get("target")
                last_ok_archive = ev.get("archive")

    if last_ok_ts == 0.0:
        print("[verify:recent] FAIL — no successful backup events in log")
        return 1

    age = time.time() - last_ok_ts
    if age > RECENT_MAX_AGE_S:
        print(
            f"[verify:recent] FAIL — last ok {age/3600:.1f}h ago "
            f"(max {RECENT_MAX_AGE_S/3600:.1f}h) target={last_ok_target}"
        )
        return 1

    print(
        f"[verify:recent] OK — last ok {age/3600:.1f}h ago · "
        f"target={last_ok_target} · {last_ok_archive}"
    )
    return 0


def _newest_local_archive() -> Path | None:
    if not LOCAL_DEST.exists():
        return None
    cands = sorted(LOCAL_DEST.glob("swarm-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def cmd_extract(archive_arg: str | None) -> int:
    if archive_arg:
        archive = Path(archive_arg)
    else:
        archive = _newest_local_archive()
        if archive is None:
            print(f"[verify:extract] FAIL — no archives found in {LOCAL_DEST}")
            return 1

    if not archive.exists():
        print(f"[verify:extract] FAIL — archive not found: {archive}")
        return 2

    print(f"[verify:extract] archive: {archive}")

    # SHA256 sidecar check.
    sha_file = archive.with_suffix(archive.suffix + ".sha256")
    if sha_file.exists():
        try:
            r = subprocess.run(
                ["sha256sum", "--check", "--status", sha_file.name],
                cwd=str(archive.parent),
                check=False,
            )
            if r.returncode != 0:
                print("[verify:extract] FAIL — sha256 mismatch")
                return 1
            print("[verify:extract] sha256 ok")
        except FileNotFoundError:
            print("[verify:extract] WARN — sha256sum not on PATH, skipping")

    scratch = Path(tempfile.mkdtemp(prefix="swarm-restore-test-"))
    try:
        r = subprocess.run(
            ["tar", "-xzf", str(archive), "-C", str(scratch)],
            check=False,
        )
        if r.returncode != 0:
            print(f"[verify:extract] FAIL — tar -xzf rc={r.returncode}")
            return 1

        # The DB snapshot lives at db-snapshot/swarm_memory.db inside archive.
        db_path = scratch / "db-snapshot" / "swarm_memory.db"
        if not db_path.exists():
            # Fall back to top-level if older format.
            db_path = scratch / "swarm_memory.db"
        if not db_path.exists():
            print("[verify:extract] FAIL — no swarm_memory.db inside archive")
            return 1

        print(f"[verify:extract] DB snapshot: {db_path} ({db_path.stat().st_size} bytes)")

        # Integrity check.
        con = sqlite3.connect(str(db_path))
        try:
            row = con.execute("PRAGMA integrity_check;").fetchone()
            if not row or row[0] != "ok":
                print(f"[verify:extract] FAIL — integrity_check returned {row}")
                return 1
            print("[verify:extract] integrity_check ok")

            # Sanity: required tables non-empty.
            for table, min_rows in SANITY_TABLES:
                try:
                    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.OperationalError:
                    print(f"[verify:extract] FAIL — table missing: {table}")
                    return 1
                if n < min_rows:
                    print(f"[verify:extract] FAIL — {table} has {n} rows (need ≥{min_rows})")
                    return 1
                print(f"[verify:extract] sanity {table}: {n} rows")
        finally:
            con.close()

        print("[verify:extract] OK")
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    sub = argv[1]
    if sub == "recent":
        return cmd_recent()
    if sub == "extract":
        return cmd_extract(argv[2] if len(argv) >= 3 else None)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
