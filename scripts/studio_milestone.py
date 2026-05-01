#!/usr/bin/env python3
"""Record a readable milestone inside P-00221285D1 so Spotlight can find
the story later. Two effects per milestone:

  1) Blackboard note (kind=milestone) — the human-readable story.
  2) Step status update for the matching [PACKET-XX] epic if requested.

Usage (library mode preferred):

    from scripts.studio_milestone import log_milestone
    log_milestone(
        packet="PACKET-04",
        title="Project overview tab live",
        status="done",          # 'doing' | 'done' | None to skip status
        story=\"\"\"... narrative ...\"\"\",
    )

CLI mode:
    python3 scripts/studio_milestone.py --packet PACKET-04 \\
            --title "..." --status done --file /tmp/story.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Iterable, Optional, Set, Tuple

API = "http://localhost:5050"
PROJECT = "P-00221285D1"

# ──────────────────────────────────────────────────────────────────────
# Brain auto-linking — every milestone story is scanned for record IDs
# and packet tags so the knowledge-center graph stays alive without
# anyone manually adding edges. This is the loop the user calls "Seven
# guiding you to where to look": as new milestones reference records,
# those records gain incoming back-edges and Spotlight discovery
# improves automatically.
# ──────────────────────────────────────────────────────────────────────

# Record-ID prefixes we care about. Each prefix maps to a record kind
# in the platinum store. Anything not in this map is ignored.
_ID_PREFIX_KIND = {
    "B-":  "note",       # blackboard / milestone notes
    "S-":  "step",
    "P-":  "project",
    "PR-": "proposal",
    "T-":  "ticket",
    "TC-": "case",
    "TR-": "test_run",
    "D-":  "doc",
    "TH-": "thread",
}
# Match `B-XXXXXXXX`, `S-XXXXXXXX`, `PR-XXXXXXXX` etc. ID part is at
# least 6 chars hex/digit/upper to keep noise out of natural prose.
_ID_RX = re.compile(r"\b(B|S|P|PR|T|TC|TR|D|TH)-([0-9A-F]{6,})\b")
_PACKET_RX = re.compile(r"\bPACKET-(\d{2})\b")


def _extract_refs(text: str) -> Tuple[Set[Tuple[str, str]], Set[str]]:
    """Return ({(kind, id), …}, {packet_tag, …}) from free-form text."""
    record_refs: Set[Tuple[str, str]] = set()
    for m in _ID_RX.finditer(text or ""):
        prefix = f"{m.group(1)}-"
        kind = _ID_PREFIX_KIND.get(prefix)
        if not kind:
            continue
        record_refs.add((kind, f"{prefix}{m.group(2)}"))
    packets = {f"PACKET-{m.group(1)}" for m in _PACKET_RX.finditer(text or "")}
    return record_refs, packets


def _auto_link_milestone(
    note_id: Optional[str],
    text: str,
    packet_step_id: Optional[str],
    actor: str = "milestone",
) -> dict:
    """Lazy-import the records.links module and write edges from the
    milestone note to every referenced record. Failures are swallowed
    so a milestone never fails because of edge-write trouble."""
    if not note_id:
        return {"ok": False, "reason": "no_note_id"}
    try:
        from core.records.links import link
    except Exception as e:
        return {"ok": False, "reason": f"import_failed:{e}"}
    record_refs, packets = _extract_refs(text)
    edges = 0
    # Don't self-loop the note onto itself.
    record_refs.discard(("note", note_id))
    # 1) Story-mentioned record IDs → 'mentions' edges from note.
    for kind, rid in record_refs:
        try:
            link(("note", note_id), "mentions", (kind, rid), actor=actor)
            edges += 1
        except Exception:
            pass
    # 2) Packet step (the [PACKET-XX] epic this milestone belongs to)
    #    → 'documents' edge from note.
    if packet_step_id:
        try:
            link(("note", note_id), "documents", ("step", packet_step_id), actor=actor)
            edges += 1
        except Exception:
            pass
    # 3) Note also sits under the project umbrella.
    try:
        link(("note", note_id), "child_of", ("project", PROJECT), actor=actor)
        edges += 1
    except Exception:
        pass
    return {"ok": True, "edges_written": edges,
            "records": [f"{k}:{i}" for k, i in record_refs],
            "packets": sorted(packets)}


def _http(method: str, path: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", "body": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _find_packet_step(packet_tag: str) -> Optional[dict]:
    proj = _http("GET", f"/api/knowledge/projects/{PROJECT}")
    if not proj.get("ok"):
        return None
    for s in proj["project"].get("steps", []):
        title = s.get("title", "") or ""
        if title.startswith(f"[{packet_tag}]"):
            return s
    return None


def log_milestone(
    *,
    packet: str,
    title: str,
    story: str,
    status: Optional[str] = None,
) -> dict:
    """packet e.g. 'PACKET-04'. status in {'doing','done','blocked','partial'} or None."""
    body = (
        f"[{packet}] MILESTONE — {title}\n"
        f"=================================\n"
        f"{story.strip()}\n"
    )
    note = _http(
        "POST",
        f"/api/knowledge/projects/{PROJECT}/blackboard",
        {"kind": "milestone", "content": body, "author": "codex"},
    )
    out = {"note": note}
    # Resolve packet step id (used by both status update and auto-edges).
    packet_step_id: Optional[str] = None
    if status or note.get("ok"):
        step = _find_packet_step(packet)
        if step and step.get("step_id"):
            packet_step_id = step["step_id"]
    if status:
        if packet_step_id:
            patch = _http(
                "PATCH",
                f"/api/knowledge/steps/{packet_step_id}",
                {"status": status, "owner": "seven"},
            )
            out["step_id"] = packet_step_id
            out["status_patch"] = patch
        else:
            out["status_patch"] = {"ok": False, "error": f"no step matching [{packet}]"}
    # Auto-link the milestone note into the knowledge graph.
    note_id = note.get("note_id") if isinstance(note, dict) else None
    out["auto_links"] = _auto_link_milestone(
        note_id=note_id, text=body, packet_step_id=packet_step_id, actor="milestone")
    return out


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--status", choices=["doing", "done", "blocked", "partial", "todo"])
    ap.add_argument("--file", help="path to a file containing the story body")
    ap.add_argument("--story", help="inline story (use --file for long form)")
    args = ap.parse_args()
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            story = fh.read()
    elif args.story:
        story = args.story
    else:
        story = sys.stdin.read()
    res = log_milestone(packet=args.packet, title=args.title, story=story, status=args.status)
    print(json.dumps(res, indent=2))
    return 0 if res.get("note", {}).get("ok") else 1


if __name__ == "__main__":
    sys.exit(_cli())
