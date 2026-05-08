#!/usr/bin/env python3
"""
scripts/vortex_restore.py — PACKET-10A Vortex emergency restore helper.

The user explicitly flagged Vortex (`time_checkpoints` + auto vortex-* git
tags) as a tier-1 must-not-lose system. This helper extracts the
`time_checkpoints` table from any swarm backup tarball into a standalone
SQLite file you can inspect, diff against the live DB, or copy table contents
back into a recovered DB.

Usage:
    python3 scripts/vortex_restore.py inspect [<archive>]
        Show summary: row count, first/last checkpoint timestamps.

    python3 scripts/vortex_restore.py extract [<archive>] [<output_db>]
        Write a new SQLite file containing only time_checkpoints from the
        archive's DB snapshot. Default output:
        /tmp/vortex-from-<stamp>.sqlite

This script is read-only with respect to the live swarm_memory.db.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

LOCAL_DEST = Path.home() / "swarm-backups"


def _newest() -> Path | None:
    if not LOCAL_DEST.exists():
        return None
    cands = sorted(LOCAL_DEST.glob("swarm-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def _extract_db(archive: Path) -> tuple[Path, Path]:
    scratch = Path(tempfile.mkdtemp(prefix="vortex-restore-"))
    r = subprocess.run(
        ["tar", "-xzf", str(archive), "-C", str(scratch),
         "./db-snapshot/swarm_memory.db"],
        check=False, capture_output=True, text=True,
    )
    if r.returncode != 0:
        shutil.rmtree(scratch, ignore_errors=True)
        raise SystemExit(f"tar extract failed rc={r.returncode}: {r.stderr}")
    db = scratch / "db-snapshot" / "swarm_memory.db"
    if not db.exists():
        shutil.rmtree(scratch, ignore_errors=True)
        raise SystemExit(f"no db-snapshot/swarm_memory.db inside {archive}")
    return scratch, db


def cmd_inspect(arg: str | None) -> int:
    archive = Path(arg) if arg else _newest()
    if not archive or not archive.exists():
        print(f"[vortex] no archive (asked: {arg!r})")
        return 1
    print(f"[vortex] archive: {archive}")
    scratch, db = _extract_db(archive)
    try:
        con = sqlite3.connect(str(db))
        n, first_ts, last_ts, last_name = con.execute("""
            SELECT COUNT(*),
                   MIN(created_at),
                   MAX(created_at),
                   (SELECT checkpoint_name FROM time_checkpoints
                    ORDER BY created_at DESC LIMIT 1)
              FROM time_checkpoints
        """).fetchone()
        print(f"[vortex] checkpoints: {n}")
        print(f"[vortex] earliest:    {first_ts}")
        print(f"[vortex] latest:      {last_ts} ({last_name})")
        con.close()
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def cmd_extract(arg_archive: str | None, arg_out: str | None) -> int:
    archive = Path(arg_archive) if arg_archive else _newest()
    if not archive or not archive.exists():
        print(f"[vortex] no archive (asked: {arg_archive!r})")
        return 1
    out = Path(arg_out) if arg_out else Path(f"/tmp/vortex-from-{archive.stem}.sqlite")
    scratch, db = _extract_db(archive)
    try:
        # Open backed-up DB read-only, attach the destination, copy schema+rows.
        if out.exists():
            out.unlink()
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dst = sqlite3.connect(str(out))
        # Copy the CREATE TABLE statement verbatim.
        ddl_row = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='time_checkpoints'"
        ).fetchone()
        if not ddl_row:
            print("[vortex] FAIL — no time_checkpoints table in archive DB")
            return 1
        dst.execute(ddl_row[0])
        rows = list(src.execute("SELECT * FROM time_checkpoints"))
        if rows:
            placeholders = ",".join(["?"] * len(rows[0]))
            dst.executemany(f"INSERT INTO time_checkpoints VALUES ({placeholders})", rows)
        dst.commit()
        dst.close()
        src.close()
        print(f"[vortex] OK — {len(rows)} checkpoints → {out}")
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    sub = argv[1]
    if sub == "inspect":
        return cmd_inspect(argv[2] if len(argv) >= 3 else None)
    if sub == "extract":
        return cmd_extract(
            argv[2] if len(argv) >= 3 else None,
            argv[3] if len(argv) >= 4 else None,
        )
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
