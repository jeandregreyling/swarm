#!/usr/bin/env python3
"""Plan-mode Git/cloud sync audit.

Non-destructive checks only:
- branch/upstream/ahead/behind
- working tree cleanliness summary
- remote auth probe (ls-remote)
- writes JSON report under runtime/reports
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "runtime" / "reports"


def _run(cmd, timeout=20) -> Dict[str, object]:
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "ok": r.returncode == 0,
            "rc": r.returncode,
            "stdout": (r.stdout or "").strip(),
            "stderr": (r.stderr or "").strip(),
        }
    except Exception as exc:
        return {"ok": False, "rc": 1, "stdout": "", "stderr": str(exc)}


def main() -> int:
    branch = _run(["git", "branch", "--show-current"]) 
    upstream = _run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    status_short = _run(["git", "status", "--short"])
    counts = _run(["git", "status", "--porcelain"])

    ahead = behind = None
    if upstream.get("ok"):
        ab = _run(["git", "rev-list", "--left-right", "--count", f"{upstream['stdout']}...HEAD"])
        if ab.get("ok") and ab.get("stdout"):
            parts = ab["stdout"].split()
            if len(parts) >= 2:
                behind = int(parts[0])
                ahead = int(parts[1])

    ssh_cmd = "ssh -o BatchMode=yes -o ConnectTimeout=5"
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = ssh_cmd
    try:
        remote_probe = subprocess.run(
            ["git", "ls-remote", "--heads", "origin"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=env,
        )
        remote_auth_ok = remote_probe.returncode == 0
        remote_err = (remote_probe.stderr or "").strip()
    except Exception as exc:
        remote_auth_ok = False
        remote_err = str(exc)

    modified = 0
    untracked = 0
    staged = 0
    for line in (counts.get("stdout") or "").splitlines():
        if not line:
            continue
        x, y = line[0], line[1]
        if x != " " and x != "?":
            staged += 1
        if y != " " and y != "?":
            modified += 1
        if x == "?" or y == "?":
            untracked += 1

    payload = {
        "timestamp": int(time.time()),
        "branch": branch.get("stdout") or "",
        "upstream": upstream.get("stdout") if upstream.get("ok") else "",
        "ahead": ahead,
        "behind": behind,
        "remote_auth_ok": remote_auth_ok,
        "remote_error": remote_err,
        "working_tree": {
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
            "clean": (staged + modified + untracked) == 0,
        },
        "status_short_preview": (status_short.get("stdout") or "").splitlines()[:120],
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(payload["timestamp"]))
    out = REPORT_DIR / f"plan_mode_git_sync_audit_{stamp}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "report_file": str(out), "remote_auth_ok": remote_auth_ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
