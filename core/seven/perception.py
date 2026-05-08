"""core.seven.perception — Seven's read-only view of the swarm.

The functions here are the *only* sanctioned cross-surface read path going
forward. New surfaces should call ``observe(focus=...)`` instead of stitching
together blackboard notes + record links + step queries themselves.

All functions are pure-read. They never mutate the DB, never write edges,
never trigger side effects.
"""
from __future__ import annotations

import sqlite3
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from core.records.links import outgoing, incoming, Edge
from core.records.store import LINKS_DB

# ── small helpers ───────────────────────────────────────────────────────────

def _swarm_conn() -> sqlite3.Connection:
    from utils.db._connection import get_connection
    return get_connection()


def _kind_of(record_id: str) -> Optional[str]:
    """Best-effort kind inference from ID prefix. Mirrors studio_milestone."""
    prefixes = {
        "B-": "note", "S-": "step", "P-": "project", "PR-": "proposal",
        "T-": "ticket", "TC-": "case", "TR-": "test_run", "D-": "doc", "TH-": "thread",
    }
    for pfx, kind in prefixes.items():
        if record_id.startswith(pfx):
            return kind
    return None


# ── core: related() — the graph traversal API ───────────────────────────────

def related(
    kind: str,
    record_id: str,
    *,
    depth: int = 1,
    group_by_rel: bool = True,
    limit_per_rel: int = 25,
) -> Dict[str, Any]:
    """Return everything connected to (kind, record_id).

    Parameters
    ----------
    kind, record_id
        The focus record.
    depth
        1 = direct neighbours only. 2 = also the neighbours-of-neighbours
        (deduped, second-hop edges flagged with ``"hop": 2``).
    group_by_rel
        When True (default), result is a dict keyed by relation name.
        When False, result is a flat list of edge dicts.
    limit_per_rel
        Cap per relation to keep responses sane on hub records.

    Returns
    -------
    dict with keys:
        focus      : {"kind", "id"}
        outgoing   : grouped or flat list (hop=1)
        incoming   : grouped or flat list (hop=1)
        hop2       : list of edges discovered at depth 2 (only when depth>=2)
        counts     : per-relation totals across all hops
    """
    out_edges: List[Edge] = list(outgoing(kind, record_id))
    in_edges: List[Edge] = list(incoming(kind, record_id))

    counts: Counter = Counter()
    for e in out_edges:
        counts[e.rel] += 1
    for e in in_edges:
        counts[f"~{e.rel}"] += 1

    hop2: List[Dict[str, Any]] = []
    if depth >= 2:
        seen: set = {(kind, record_id)}
        for e in out_edges:
            seen.add((e.dst_kind, e.dst_id))
        for e in in_edges:
            seen.add((e.src_kind, e.src_id))

        # Walk one more hop from each direct neighbour.
        for e in out_edges:
            for h in outgoing(e.dst_kind, e.dst_id):
                key = (h.dst_kind, h.dst_id)
                if key in seen:
                    continue
                seen.add(key)
                d = h.as_dict()
                d["hop"] = 2
                d["via"] = {"kind": e.dst_kind, "id": e.dst_id}
                hop2.append(d)

    def _shape(edges: List[Edge]) -> Any:
        if not group_by_rel:
            return [e.as_dict() for e in edges]
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for e in edges:
            if len(grouped[e.rel]) < limit_per_rel:
                grouped[e.rel].append(e.as_dict())
        return dict(grouped)

    return {
        "focus": {"kind": kind, "id": record_id},
        "outgoing": _shape(out_edges),
        "incoming": _shape(in_edges),
        "hop2": hop2,
        "counts": dict(counts),
    }


# ── recent activity (system-wide pulse) ─────────────────────────────────────

def recent(*, limit: int = 25, kinds: Optional[Tuple[str, ...]] = None) -> List[Dict[str, Any]]:
    """Return the most recent blackboard notes across the swarm.

    This is Seven's "what just happened" feed. Source is project_blackboard_notes
    (the canonical narrative spine). Each row carries kind, project, title, and
    an estimate of how many auto-edges it produced.
    """
    sql = (
        "SELECT note_id, project_id, kind, content, created_at, author, status "
        "FROM project_blackboard_notes "
    )
    params: List[Any] = []
    if kinds:
        placeholders = ",".join(["?"] * len(kinds))
        sql += f"WHERE kind IN ({placeholders}) "
        params.extend(kinds)
    sql += "ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))

    conn = _swarm_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    out: List[Dict[str, Any]] = []
    for r in rows:
        # rows here are sqlite3.Row OR tuple depending on row_factory; handle both.
        try:
            d = dict(r)
        except (TypeError, ValueError):
            d = {
                "note_id": r[0], "project_id": r[1], "kind": r[2],
                "content": r[3], "created_at": r[4], "author": r[5], "status": r[6],
            }
        # Derive a title from the first non-empty line of content.
        content = (d.get("content") or "").strip()
        first_line = content.split("\n", 1)[0].strip() if content else ""
        d["title"] = first_line[:120] if first_line else f"({d.get('kind','note')})"
        edge_count = 0
        try:
            edge_count = sum(1 for _ in outgoing("note", d.get("note_id") or ""))
        except Exception:
            pass
        d["edge_count"] = edge_count
        out.append(d)
    return out


# ── open steps (what's on the plate) ────────────────────────────────────────

def open_steps(
    *,
    project_id: Optional[str] = None,
    statuses: Tuple[str, ...] = ("todo", "doing"),
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return open steps, newest first. Filterable by project."""
    placeholders = ",".join(["?"] * len(statuses))
    sql = (
        f"SELECT step_id, project_id, title, status, owner, created_at, updated_at "
        f"FROM project_steps WHERE status IN ({placeholders}) "
    )
    params: List[Any] = list(statuses)
    if project_id:
        sql += "AND project_id = ? "
        params.append(project_id)
    sql += "ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?"
    params.append(int(limit))

    conn = _swarm_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        try:
            out.append(dict(r))
        except (TypeError, ValueError):
            out.append({
                "step_id": r[0], "project_id": r[1], "title": r[2],
                "status": r[3], "owner": r[4],
                "created_at": r[5], "updated_at": r[6],
            })
    return out


# ── system stats (Seven's vital signs) ──────────────────────────────────────

def stats() -> Dict[str, Any]:
    """Aggregate counts that describe the shape of the swarm right now."""
    out: Dict[str, Any] = {"as_of": time.time()}

    # Edge graph
    try:
        c = sqlite3.connect(LINKS_DB)
        try:
            total_edges = c.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
            by_rel = c.execute(
                "SELECT rel, COUNT(*) FROM record_links GROUP BY rel ORDER BY 2 DESC"
            ).fetchall()
            distinct_records = c.execute(
                "SELECT COUNT(DISTINCT src_kind || ':' || src_id) FROM record_links"
            ).fetchone()[0]
        finally:
            c.close()
        out["graph"] = {
            "total_edges": total_edges,
            "distinct_records": distinct_records,
            "by_rel": [{"rel": r, "n": n} for r, n in by_rel],
        }
    except Exception as e:
        out["graph"] = {"error": str(e)}

    # Steps
    try:
        conn = _swarm_conn()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM project_steps GROUP BY status"
            ).fetchall()
        finally:
            conn.close()
        out["steps"] = {row[0]: row[1] for row in rows}
        out["steps_open"] = out["steps"].get("todo", 0) + out["steps"].get("doing", 0)
    except Exception as e:
        out["steps"] = {"error": str(e)}

    # Blackboard
    try:
        conn = _swarm_conn()
        try:
            rows = conn.execute(
                "SELECT kind, COUNT(*) FROM project_blackboard_notes GROUP BY kind"
            ).fetchall()
        finally:
            conn.close()
        out["blackboard"] = {row[0]: row[1] for row in rows}
    except Exception as e:
        out["blackboard"] = {"error": str(e)}

    return out


# ── observe() — the headline endpoint ───────────────────────────────────────

def observe(
    *,
    focus: Optional[str] = None,
    limit_recent: int = 10,
    limit_open: int = 12,
) -> Dict[str, Any]:
    """One call returns a complete snapshot of what Seven sees.

    ``focus`` may be a record id (e.g. "S-88A6C8C18A") or "kind:id". When
    omitted, returns a system-wide snapshot.
    """
    snapshot: Dict[str, Any] = {
        "as_of": time.time(),
        "focus": None,
        "stats": stats(),
        "recent": recent(limit=limit_recent),
        "open_steps": open_steps(limit=limit_open),
    }

    if focus:
        if ":" in focus:
            kind, rid = focus.split(":", 1)
        else:
            rid = focus
            kind = _kind_of(rid)
        if kind:
            snapshot["focus"] = {"kind": kind, "id": rid}
            snapshot["related"] = related(kind, rid, depth=1)
        else:
            snapshot["focus"] = {"kind": None, "id": rid, "note": "unknown id prefix"}

    # Suggestions are propose-only nudges built from the above.
    try:
        from .suggest import suggestions as _suggest
        snapshot["suggestions"] = _suggest(snapshot)
    except Exception as e:
        snapshot["suggestions"] = {"error": str(e), "items": []}

    return snapshot
