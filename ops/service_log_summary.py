"""ops/service_log_summary.py — Summarize recent journalctl errors.

S-6D75823AEC (P-00221285D1 PACKET-05). Collects the last N error/warning
lines for every swarm-* systemd unit into one report. Read-only, safe on
hot box.

Usage:
    python -m ops.service_log_summary                # last hour, all units
    python -m ops.service_log_summary --since 6h     # custom window
    python -m ops.service_log_summary --json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from typing import Any


SERVICES = (
    "swarm-terminal",
    "swarm-listener",
    "swarm-fridays",
    "swarm-discord",
    "swarm-telegram",
    "swarm-prewarm",
)

ERROR_RE = re.compile(
    r"\b(error|err|fail|failed|exception|traceback|critical|fatal)\b",
    re.IGNORECASE,
)


def journal_lines(unit: str, since: str, max_lines: int = 80) -> list[str]:
    if not shutil.which("journalctl"):
        return []
    try:
        proc = subprocess.run(
            ["journalctl", "--no-pager", "--since", since, "-u", unit, "-n", "500"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    out: list[str] = []
    for line in proc.stdout.splitlines():
        if ERROR_RE.search(line):
            out.append(line)
            if len(out) >= max_lines:
                break
    return out


def collect(since: str, max_lines: int = 20) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "since": since,
        "units": [],
    }
    total = 0
    for unit in SERVICES:
        lines = journal_lines(unit, since=since, max_lines=max_lines)
        summary["units"].append({"name": unit, "error_count": len(lines), "tail": lines[-max_lines:]})
        total += len(lines)
    summary["total_error_lines"] = total
    summary["overall_ok"] = total == 0
    return summary


def render_text(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    status = "GREEN" if summary["overall_ok"] else "AMBER/RED"
    lines.append(
        f"=== swarm-* journal errors [{status}] since={summary['since']} "
        f"total={summary['total_error_lines']} {summary['generated_at']} ==="
    )
    for unit in summary["units"]:
        if unit["error_count"]:
            lines.append(f"\n[{unit['name']}] {unit['error_count']} error/warn line(s)")
            for line in unit["tail"]:
                lines.append(f"  {line}")
        else:
            lines.append(f"[{unit['name']}] clean")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Swarm service log summary")
    parser.add_argument("--since", default="1h", help="journalctl --since window (e.g. 1h, 6h, today)")
    parser.add_argument("--max-lines", type=int, default=20, help="max error lines per unit")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)
    summary = collect(since=args.since, max_lines=args.max_lines)
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(render_text(summary))
    return 0 if summary["overall_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
