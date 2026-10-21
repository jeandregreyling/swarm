"""core.seven.suggest — propose-only nudges built from a perception snapshot.

Seven does not act unprompted. ``suggestions`` reads an observation snapshot
and returns small, addressable hints surfaces can render (Spotlight rows,
sparkles next to a tile, etc.). Each item is a dict with:

    { "id": "<stable hash>",
      "kind": "open_step" | "stale_doing" | "hub" | "untouched_today",
      "label": "<one-line human text>",
      "detail": "<longer explanation>",
      "target": {"kind": "...", "id": "..."} | null,
      "weight": 0.0..1.0 }

These are deliberately mild: they describe the current shape, they do not
trigger anything.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List


def _id(parts: str) -> str:
    return "SUG-" + hashlib.sha1(parts.encode("utf-8")).hexdigest()[:10].upper()


def suggestions(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    now = time.time()

    open_steps = snapshot.get("open_steps") or []
    recent_notes = snapshot.get("recent") or []
    stats = snapshot.get("stats") or {}

    # 1) Stale "doing" steps — anything in 'doing' that hasn't moved in >7 days.
    week = 7 * 86400
    for s in open_steps:
        if s.get("status") != "doing":
            continue
        ts = s.get("updated_at") or s.get("created_at") or 0
        if ts and (now - ts) > week:
            sid = s.get("step_id")
            items.append({
                "id": _id("stale:" + str(sid)),
                "kind": "stale_doing",
                "label": f"Step in 'doing' for >7d: {s.get('title','')[:80]}",
                "detail": f"{sid} hasn't moved since {int((now - ts)/86400)}d ago.",
                "target": {"kind": "step", "id": sid},
                "weight": 0.7,
            })

    # 2) Earliest open step — Seven's "next thing" hint.
    if open_steps:
        earliest = open_steps[-1]  # list is newest-first; oldest is last
        sid = earliest.get("step_id")
        items.append({
            "id": _id("next:" + str(sid)),
            "kind": "open_step",
            "label": f"Oldest open: {earliest.get('title','')[:80]}",
            "detail": f"{sid} ({earliest.get('status')}). May be worth closing or pruning.",
            "target": {"kind": "step", "id": sid},
            "weight": 0.4,
        })

    # 3) Recent milestone with most edges → "active surface" hint.
    if recent_notes:
        hot = max(recent_notes, key=lambda n: int(n.get("edge_count") or 0))
        if int(hot.get("edge_count") or 0) >= 3:
            nid = hot.get("note_id")
            items.append({
                "id": _id("hub:" + str(nid)),
                "kind": "hub",
                "label": f"Active hub: {hot.get('title','')[:80]}",
                "detail": f"{nid} touched {hot.get('edge_count')} records — likely worth a follow-up.",
                "target": {"kind": "note", "id": nid},
                "weight": 0.5,
            })

    # 4) Graph health vital sign.
    g = stats.get("graph") or {}
    if isinstance(g, dict) and "total_edges" in g:
        items.append({
            "id": _id("vitals"),
            "kind": "vitals",
            "label": (
                f"Graph: {g.get('total_edges', 0)} edges across "
                f"{g.get('distinct_records', 0)} records · "
                f"{stats.get('steps_open', 0)} open steps"
            ),
            "detail": "Seven's perception layer is online.",
            "target": None,
            "weight": 0.2,
        })

    # 5) Focused observation — if a focus is given and has lots of relations.
    focus = snapshot.get("focus") or {}
    rel = snapshot.get("related") or {}
    if focus.get("id") and rel.get("counts"):
        total = sum(int(v) for v in rel["counts"].values())
        if total:
            items.append({
                "id": _id("focus:" + str(focus["id"])),
                "kind": "focus",
                "label": f"{focus['kind']}:{focus['id']} touches {total} other records",
                "detail": ", ".join(f"{k}×{v}" for k, v in rel["counts"].items()),
                "target": focus,
                "weight": 0.6,
            })

    # Sort by weight (descending), cap to a digestible count.
    items.sort(key=lambda x: -float(x.get("weight") or 0))
    return {"items": items[:12], "count": len(items)}
