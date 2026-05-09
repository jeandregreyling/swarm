"""ops.mega_backlog — list active mega-projects with a one-line health
summary so an operator can see the full backlog at a glance.

S-37A1AD9E04 — Consolidate active mega-project backlog.

Usage:
    python -m ops.mega_backlog                # default db
    python -m ops.mega_backlog --db PATH      # custom db
    python -m ops.mega_backlog --json         # machine-readable

Prints, per active project:
    P-XXXX  Name (status)  done/total  todo=N  blocked=N  evidence=N
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List


def lane_for_step(title: str, owner: str = "") -> str:
    """Return a stable workstream lane label for a backlog step."""
    blob = f"{title or ''} {owner or ''}".lower()
    if "watchdog" in blob or "thread #" in blob or "chat257" in blob:
        return "watchdog-recovery"
    if "[packet-11]" in blob or "media center" in blob or "media " in blob:
        return "media"
    if "[p-441a6d6476]" in blob or "v8-" in blob or "seven runtime" in blob:
        return "v8-runtime"
    if "[wishlist]" in blob:
        return "wishlist-capture"
    if "[money-hub]" in blob or "newsletter" in blob:
        return "money-hub"
    if "[runtime]" in blob or "airllm" in blob:
        return "runtime-research"
    if "[md:bugs]" in blob or "bug-" in blob:
        return "bugfix"
    if "cleanup" in blob or "retire" in blob or "legacy db" in blob or "consolidate" in blob:
        return "cleanup"
    return "general"


def collect(conn) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT project_id, name, status FROM projects "
        "WHERE status IN ('active','on_hold') "
        "ORDER BY status, project_id"
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for pid, name, status in rows:
        steps = conn.execute(
            "SELECT title, status, COALESCE(owner,'') FROM project_steps WHERE project_id=?",
            (pid,),
        ).fetchall()
        counts = {"total": 0, "done": 0, "blocked": 0, "todo": 0, "skipped": 0}
        lanes: Dict[str, Dict[str, int]] = {}
        for title, st, owner in steps:
            n = 1
            lane = lane_for_step(title, owner)
            lane_counts = lanes.setdefault(
                lane,
                {"total": 0, "done": 0, "blocked": 0, "todo": 0, "doing": 0, "skipped": 0},
            )
            lane_counts["total"] += n
            key = (st or "todo").strip().lower()
            if key not in ("done", "blocked", "skipped"):
                if key == "doing":
                    lane_counts["doing"] += n
                else:
                    lane_counts["todo"] += n
                key = "todo"
            else:
                lane_counts[key] += n
            counts["total"] += n
            counts[key] = counts.get(key, 0) + n
        try:
            evidence = conn.execute(
                "SELECT COUNT(*) FROM project_step_evidence WHERE project_id=?",
                (pid,),
            ).fetchone()[0]
        except Exception:
            evidence = 0
        out.append({
            "project_id": pid,
            "name": name,
            "status": status,
            "step_counts": counts,
            "lanes": dict(sorted(lanes.items())),
            "evidence_count": int(evidence),
            "completion_pct": (
                round(100.0 * counts["done"] / counts["total"], 1)
                if counts["total"] else 0.0
            ),
        })
    return out


def render_text(records: List[Dict[str, Any]]) -> str:
    lines = ["=== Active mega-project backlog ===", ""]
    if not records:
        lines.append("(no active or on-hold projects)")
        return "\n".join(lines)
    for r in records:
        c = r["step_counts"]
        lines.append(
            f"{r['project_id']}  {r['name'][:48]:<48}  "
            f"({r['status']})  {c['done']}/{c['total']}  "
            f"todo={c['todo']}  blocked={c.get('blocked',0)}  "
            f"evidence={r['evidence_count']}  ({r['completion_pct']}%)"
        )
        open_lanes = [
            (name, lane)
            for name, lane in (r.get("lanes") or {}).items()
            if lane.get("todo", 0) or lane.get("blocked", 0)
        ]
        for name, lane in sorted(open_lanes, key=lambda item: (-item[1].get("todo", 0), item[0]))[:8]:
            lines.append(
                f"  - {name}: {lane.get('done',0)}/{lane.get('total',0)} "
                f"open={lane.get('todo',0)} doing={lane.get('doing',0)} "
                f"blocked={lane.get('blocked',0)}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get(
        "SWARM_DB_PATH",
        os.path.join(os.path.dirname(__file__), "..", "swarm_memory.db"),
    ))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    try:
        records = collect(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(render_text(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
