#!/usr/bin/env python3
"""PACKET-06 slice 2 — dedupe duplicate backlog steps in P-00221285D1.

Strategy:
  Group open non-epic steps by (lower(title), normalized description).
  Normalization strips the leading 'Packet: PACKET-XX' prefix that the
  PACKET-06 slice-1 tagger added, and collapses whitespace. The oldest
  row (smallest created_at) wins — the rest are marked status='skipped'
  with a 'Deduped: superseded by S-XXXX' note prepended to their
  description.

Idempotent: rows already status='skipped' are excluded; if a row's
description already starts with 'Deduped:' it is left alone.

Run:
    python3 scripts/dedupe_backlog.py             # apply
    python3 scripts/dedupe_backlog.py --dry-run   # preview
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "swarm_memory.db"
PROJECT = "P-00221285D1"


def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = re.sub(r"^Packet:\s*PACKET-\d+\s*\n+", "", text.strip(), flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT step_id, title, status, description, created_at "
        "FROM project_steps WHERE project_id=? "
        "AND status IN ('todo','doing','blocked','partial') "
        "AND title NOT LIKE '[PACKET-%' "
        "ORDER BY created_at",
        (PROJECT,),
    ).fetchall()

    groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        if (r["description"] or "").startswith("Deduped:"):
            continue
        key = (r["title"].strip().lower(), normalize(r["description"]))
        groups[key].append(r)

    plans = []
    for (title, _), members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: r["created_at"])
        keeper = members[0]
        for extra in members[1:]:
            plans.append((extra["step_id"], keeper["step_id"], title, extra["description"] or ""))

    if not plans:
        print("no duplicates found — nothing to do")
        return 0

    print(f"will skip {len(plans)} duplicate row(s):")
    for sid, kid, title, _ in plans:
        print(f"  {sid}  →  superseded by {kid}    ({title[:70]})")

    if args.dry_run:
        print("(dry-run, no changes written)")
        return 0

    cur = conn.cursor()
    for sid, kid, _title, old_desc in plans:
        new_desc = f"Deduped: superseded by {kid}\n\n{old_desc}"
        cur.execute(
            "UPDATE project_steps SET status='skipped', description=?, "
            "updated_at=strftime('%s','now') WHERE step_id=?",
            (new_desc, sid),
        )
    conn.commit()
    conn.close()
    print(f"updated {len(plans)} rows → status=skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
