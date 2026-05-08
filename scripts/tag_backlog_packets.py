#!/usr/bin/env python3
"""PACKET-06 Slice 1: Tag every open step in P-00221285D1 with the packet
it belongs under. We do not rename titles (that would break idempotency
for anything reading by title); instead we stamp a 'Packet: PACKET-XX'
line at the head of the description so the new ALM detail view shows
the parent packet, and a future overview tab can group on it.

Idempotent: if the description already starts with 'Packet: ' we leave
it untouched and treat it as already-tagged.

Classification rules (first match wins, simple substring on lowered title):
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "swarm_memory.db"
PROJECT = "P-00221285D1"

RULES = [
    # PACKET-01 ingest
    ("PACKET-01", [
        r"\bmd ingest", r"\bmarkdown\b.*\bingest", r"\bdocs?\b.*\bsweep",
        r"\bdocumentation\b.*\bregistr", r"\bregister\b.*\b\.md\b",
        r"\bmove\b.*\barchive", r"\bsource of truth\b", r"\bdoc archive\b",
    ]),
    # PACKET-03 ALM detail
    ("PACKET-03", [
        r"\balm\b", r"\bopen step\b", r"\bopen case\b", r"\bopen run\b",
        r"\bopen proposal\b", r"\bdetail view\b", r"\bdrill down\b",
        r"\bdrilldown\b", r"\brunbook\b.*\bopen", r"\bdetails panel\b",
        r"\bartifact execution tests\b", r"\breal local runners\b",
    ]),
    # PACKET-04 project overview
    ("PACKET-04", [
        r"\boverview\b", r"\bdashboard\b", r"\brelationship", r"\brollup",
        r"\bproject summary\b", r"\bmilestone view\b",
    ]),
    # PACKET-02 / PACKET-08 per-record file model
    ("PACKET-02", [
        r"\bper.?record\b", r"\bfile per\b", r"\bsplit monolith\b",
        r"\bmonolith\b", r"\bfile model\b", r"\bsingle openable file\b",
    ]),
    ("PACKET-08", [
        r"\brecord store\b", r"\bartifact path\b", r"\bwriter/reader\b",
        r"\bjson per record\b",
    ]),
    # PACKET-05 architecture/system runs in itself
    ("PACKET-05", [
        r"\barchitecture\b", r"\bself.?test\b", r"\bgap audit\b",
        r"\bspine\b", r"\bvortex\b.*\bhealth", r"\bself-host", r"\brunbook\b",
        r"\bsystem.runs.in.itself\b",
    ]),
    # PACKET-07 — inter-tile sweep (catch-all for UI/UX surfaces)
    ("PACKET-07", [
        r"\bchat", r"\bterminal\b", r"\btile\b", r"\bwindow\b", r"\bdragger\b",
        r"\bdropdown\b", r"\bpopout\b", r"\bstar\b", r"\bspotlight\b",
        r"\bmic button\b", r"\bsettings tile\b", r"\btrace tile\b",
        r"\btheme\b", r"\bstudio defaults\b", r"\bstudio proposals\b",
        r"\bstudio git blocks\b", r"\bvortex\b", r"\bfeeds\b",
        r"\bdictionary\b", r"\bmain-?screen\b", r"\bmain-?terminal\b",
        r"\bquick-?access\b", r"\bhistory popout\b", r"\bfavourites\b",
        r"\benrollment\b", r"\bhealth check\b", r"\buniversal \"?\?",
        r"\b\"\?\"", r"\btasker\b", r"\bcalendar\b", r"\bagents tile\b",
        r"\bdocs/manual\b", r"\bmemory\b.*\bhive\b", r"\bthought.?bubble\b",
        r"\blocal-?agent\b.*\bbanner\b", r"\bmedia center\b",
        r"\brelay\b", r"\bui\b", r"\bicon\b", r"\bbutton\b", r"\bmenu\b",
        r"\bsidebar\b", r"\bnavbar\b", r"\bstatus bar\b",
    ]),
]


def classify(title: str, description: str) -> str:
    blob = f"{title or ''} {description or ''}".lower()
    for packet, patterns in RULES:
        for p in patterns:
            if re.search(p, blob):
                return packet
    # default fallback: PACKET-07 if it looks like UI; otherwise PACKET-05
    if any(k in blob for k in ("ui", "tile", "window", "click", "scroll", "render")):
        return "PACKET-07"
    return "PACKET-05"


def main() -> int:
    if not DB.exists():
        print(f"db missing: {DB}")
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    counts: Counter = Counter()
    skipped = 0
    examined = 0
    try:
        rows = conn.execute(
            "SELECT step_id, title, COALESCE(description,'') AS description "
            "FROM project_steps "
            "WHERE project_id=? AND status IN ('todo','doing','blocked','partial')",
            (PROJECT,),
        ).fetchall()
        with conn:
            for r in rows:
                examined += 1
                title = r["title"] or ""
                if title.startswith("[PACKET-"):
                    # the packet epics themselves
                    skipped += 1
                    continue
                desc = r["description"] or ""
                if desc.lstrip().lower().startswith("packet:"):
                    skipped += 1
                    continue
                packet = classify(title, desc)
                counts[packet] += 1
                new_desc = f"Packet: {packet}\n\n{desc}".strip()
                conn.execute(
                    "UPDATE project_steps SET description=?, updated_at=? WHERE step_id=?",
                    (new_desc, time.time(), r["step_id"]),
                )
    finally:
        conn.close()
    print(f"examined={examined} skipped={skipped}")
    for packet, n in sorted(counts.items()):
        print(f"  {packet}: {n}")
    print(f"  TOTAL TAGGED: {sum(counts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
