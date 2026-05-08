"""core.seven.reasoning — Seven's small deterministic mind.

This module is the single place where perception (the graph), memory
(episodes/beliefs/concepts), and propose-only nudges are turned into
narrative answers and ranked decisions.

Public surface
--------------

``learn(event)``
    Process one ledger-shaped event. Writes an episode, updates
    attention, runs a fixed set of belief rules. Idempotent within a
    single ``episode_id``.

``explain(focus=None)``
    Build a short narrative ("what's going on") grounded in observe(),
    relevant episodes, and beliefs. Returns ``{lines, snapshot, beliefs,
    episodes}`` so callers can render either prose or structured JSON.

``decide(intent)``
    Given a string intent — e.g. "what should I do next", "do it",
    "summarise" — return ranked proposals with rationale. Today this is
    rule-based; tomorrow it can route through a local model. Always
    propose-only: ``decide`` never mutates state.

The rules are deliberately *simple* and explicit. They are the curriculum
Seven boots from. Future learning lives in adding belief rules here, in
new concepts under ``docs/seven/``, and in episode-driven recalibration
of confidence.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from . import memory as _mem
from .perception import observe, related, recent, open_steps, stats


# ── salience scoring ────────────────────────────────────────────────────────

_SALIENCE_BY_KIND = {
    "note": 0.85,        # milestones — high signal
    "proposal": 0.70,
    "ticket": 0.65,
    "step": 0.55,
    "case": 0.55,
    "test_run": 0.50,
    "doc": 0.45,
    "thread": 0.40,
    "project": 0.30,
}


def _salience(kind: Optional[str], action: Optional[str]) -> float:
    base = _SALIENCE_BY_KIND.get(kind or "", 0.45)
    if action == "delete":
        base = min(1.0, base + 0.1)
    return base


# ── learn(event) ────────────────────────────────────────────────────────────

def learn(event: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one ledger-shaped event into memory + belief updates.

    Expected shape (from ``runtime/records/_ledger.jsonl``)::

        {"ts": float, "kind": str, "id": str, "action": "save"|"delete",
         "actor": str, "path": str}

    Returns a small dict describing what was learned.
    """
    kind = event.get("kind")
    rid = event.get("id")
    action = event.get("action") or "save"
    actor = event.get("actor") or "system"
    ts = float(event.get("ts") or time.time())

    salience = _salience(kind, action)

    eid = _mem.append_episode(
        source="ledger",
        kind=kind,
        record_id=rid,
        action=action,
        actor=actor,
        salience=salience,
        ts=ts,
        payload=event,
    )

    learned: List[str] = []

    # Rule 1: every saved record asserts an "exists" belief — small confidence,
    # high evidence count over time so beliefs about active records dominate.
    if rid and kind:
        _mem.assert_belief(f"{kind}:{rid}", "exists", "true", confidence=0.95, evidence_delta=1)
        learned.append("exists")

        # Rule 2: actor responsibility — last writer keeps a soft claim.
        _mem.assert_belief(f"{kind}:{rid}", "last_actor", actor, confidence=0.6)
        learned.append("last_actor")

    # Rule 3: high-salience saves nudge a "recently_active" belief on parent project
    if kind == "note" and rid:
        _mem.assert_belief(f"{kind}:{rid}", "is_milestone", "true", confidence=0.9)
        learned.append("is_milestone")

    # Rule 4: deletions retract "exists".
    if action == "delete" and rid and kind:
        _mem.retract_belief(f"{kind}:{rid}", "exists", "true")
        _mem.assert_belief(f"{kind}:{rid}", "deleted", "true", confidence=1.0)
        learned.append("deleted")

    return {"episode_id": eid, "learned": learned, "salience": salience}


# ── derived beliefs ─────────────────────────────────────────────────────────

def consolidate(*, max_records: int = 50) -> Dict[str, Any]:
    """Walk recent attention + open steps and write *derived* beliefs:
    is_stale, is_hub, is_active. Cheap to call; safe to run periodically.
    """
    now = time.time()
    week = 7 * 86400
    out = {"stale": 0, "hub": 0, "active": 0}

    # Stale-doing
    for s in open_steps(statuses=("doing",), limit=max_records):
        sid = s.get("step_id")
        ts = s.get("updated_at") or s.get("created_at") or 0
        if not sid or not ts:
            continue
        if (now - ts) > week:
            _mem.assert_belief(f"step:{sid}", "is_stale", "true", confidence=0.9)
            out["stale"] += 1
        else:
            _mem.retract_belief(f"step:{sid}", "is_stale", "true")

    # Hub: any record with edge-count >= 3 in recent activity
    for n in recent(limit=25):
        nid = n.get("note_id")
        ec = int(n.get("edge_count") or 0)
        if not nid:
            continue
        if ec >= 3:
            _mem.assert_belief(f"note:{nid}", "is_hub", "true", confidence=min(1.0, ec / 10.0))
            out["hub"] += 1

    # Active packets: for each PACKET-N epic that has any open child step,
    # mark active.
    snapshot = observe(limit_recent=10, limit_open=50)
    for s in snapshot.get("open_steps") or []:
        title = (s.get("title") or "")
        # detect [PACKET-N] tag in title
        if title.startswith("[PACKET-") and "]" in title:
            packet = title.split("]", 1)[0].lstrip("[")
            _mem.assert_belief(f"packet:{packet}", "is_active", "true", confidence=0.8)
            out["active"] += 1

    return out


# ── explain(focus) ──────────────────────────────────────────────────────────

def _pick_kind(rid: str) -> Optional[str]:
    prefixes = {
        "B-": "note", "S-": "step", "P-": "project", "PR-": "proposal",
        "T-": "ticket", "TC-": "case", "TR-": "test_run", "D-": "doc", "TH-": "thread",
    }
    for pfx, k in prefixes.items():
        if rid.startswith(pfx):
            return k
    return None


def explain(focus: Optional[str] = None, *, limit_episodes: int = 8) -> Dict[str, Any]:
    """Narrative answer to "what's going on" / "tell me about X".

    If ``focus`` is provided as a record id (e.g. ``S-XYZ``), the answer is
    grounded on that record's neighbours, recent episodes, and beliefs.
    Otherwise it's a vital-signs style overview.
    """
    snapshot = observe(focus=focus or None, limit_recent=8, limit_open=8)
    lines: List[str] = []
    beliefs: List[Dict[str, Any]] = []
    episodes: List[Dict[str, Any]] = []

    g = (snapshot.get("stats") or {}).get("graph") or {}
    s_open = (snapshot.get("stats") or {}).get("steps_open")
    lines.append(
        f"I see {g.get('total_edges', 0)} edges across {g.get('distinct_records', 0)} "
        f"records, with {s_open if s_open is not None else '?'} open steps."
    )

    if focus:
        kind = _pick_kind(focus) or "record"
        rel = snapshot.get("related") or {}
        counts = rel.get("counts") or {}
        if counts:
            top = sorted(counts.items(), key=lambda kv: -int(kv[1]))[:3]
            top_s = ", ".join(f"{k} ×{v}" for k, v in top)
            lines.append(f"{kind} {focus} sits at the centre of: {top_s}.")
        else:
            lines.append(f"{kind} {focus} has no graph edges yet.")

        episodes = _mem.recall_episodes(record_id=focus, limit=limit_episodes)
        if episodes:
            last = episodes[0]
            ago = max(0, int((time.time() - float(last.get("ts") or 0)) / 60))
            lines.append(
                f"Last touched {ago}m ago by {last.get('actor','?')} "
                f"({last.get('action','?')})."
            )

        beliefs = _mem.beliefs_about(subject=f"{kind}:{focus}", limit=10)
        if beliefs:
            top_b = beliefs[0]
            obj = f" → {top_b['object']}" if top_b.get("object") else ""
            lines.append(
                f"Belief: {top_b['predicate']}{obj} "
                f"(confidence {top_b['confidence']:.2f}, n={top_b['evidence_count']})."
            )
    else:
        sugs = (snapshot.get("suggestions") or {}).get("items") or []
        if not sugs:
            # if observe didn't include suggestions, try direct
            from .suggest import suggestions as _sug
            sugs = (_sug(snapshot) or {}).get("items") or []
        if sugs:
            top = sugs[0]
            lines.append(f"Top nudge: {top.get('label','')}.")
        episodes = _mem.recall_episodes(limit=limit_episodes)
        if episodes:
            last = episodes[0]
            ago = max(0, int((time.time() - float(last.get("ts") or 0)) / 60))
            lines.append(
                f"Last system event {ago}m ago: "
                f"{last.get('action','?')} on {last.get('kind')}:{last.get('record_id')}."
            )
        beliefs = _mem.beliefs_about(predicate="is_active", limit=5)

    return {
        "lines": lines,
        "snapshot": snapshot,
        "episodes": episodes,
        "beliefs": beliefs,
        "memory": _mem.memory_stats(),
    }


# ── decide(intent) ──────────────────────────────────────────────────────────

_INTENT_ALIASES = {
    "what's going on": "status",
    "whats going on": "status",
    "status": "status",
    "summary": "status",
    "vitals": "status",
    "what should i do next": "next",
    "what should i do": "next",
    "next": "next",
    "do it": "do",
    "act": "do",
    "remember": "remember",
    "what do you know about": "remember",
}


def _normalise_intent(intent: str) -> str:
    s = (intent or "").strip().lower().rstrip("?.! ")
    if s in _INTENT_ALIASES:
        return _INTENT_ALIASES[s]
    for needle, target in _INTENT_ALIASES.items():
        if s.startswith(needle):
            return target
    return s or "status"


def decide(intent: str, *, focus: Optional[str] = None) -> Dict[str, Any]:
    """Return a ranked list of proposals for an intent.

    Output shape::

        {
          "intent": "next",
          "proposals": [
            {"action": "review", "target": {"kind":"step","id":"S-..."},
             "rationale": "...", "confidence": 0.7},
            ...
          ],
          "authority": "propose-only",
          "would_dispatch_to": null
        }
    """
    norm = _normalise_intent(intent)
    proposals: List[Dict[str, Any]] = []

    if norm == "status":
        ex = explain(focus=focus)
        return {
            "intent": "status",
            "narrative": ex["lines"],
            "proposals": [],
            "authority": "propose-only",
        }

    if norm == "next":
        snapshot = observe(focus=focus or None, limit_recent=8, limit_open=12)
        from .suggest import suggestions as _sug
        items = (_sug(snapshot) or {}).get("items") or []
        # Up to 5 strongest, weight desc
        for it in sorted(items, key=lambda x: -float(x.get("weight") or 0))[:5]:
            proposals.append({
                "action": "review",
                "target": it.get("target"),
                "rationale": it.get("detail") or it.get("label"),
                "confidence": float(it.get("weight") or 0.0),
                "kind": it.get("kind"),
                "label": it.get("label"),
            })
        # Fallback: oldest open step
        if not proposals:
            for s in (open_steps(limit=1) or []):
                proposals.append({
                    "action": "review",
                    "target": {"kind": "step", "id": s.get("step_id")},
                    "rationale": "Oldest open step.",
                    "confidence": 0.4,
                    "kind": "open_step",
                    "label": s.get("title"),
                })
        return {
            "intent": "next",
            "proposals": proposals,
            "authority": "propose-only",
        }

    if norm == "do":
        # Authority gate: Seven is propose-only. Return what it *would*
        # propose if asked, but explicitly does not act.
        plan = decide("next", focus=focus)
        plan["intent"] = "do"
        plan["authority"] = "propose-only"
        plan["refused"] = True
        plan["refused_reason"] = (
            "Seven is in propose-only mode. Confirm the proposal and the "
            "owning surface will dispatch."
        )
        return plan

    if norm == "remember":
        # Concept lookup
        from . import memory as _m
        q = (intent or "").lower()
        for prefix in ("what do you know about", "remember", "tell me about", "explain"):
            if q.startswith(prefix):
                q = q[len(prefix):].strip()
        hits = _m.search_concepts(q, limit=5) if q else _m.list_concepts(limit=5)
        return {
            "intent": "remember",
            "query": q,
            "concepts": hits,
            "authority": "propose-only",
        }

    # unknown intent — fall back to status
    return {
        "intent": norm,
        "fallback": "status",
        "narrative": explain(focus=focus)["lines"],
        "authority": "propose-only",
    }
