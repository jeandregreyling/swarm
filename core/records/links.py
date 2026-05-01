"""core.records.links — Platinum layer typed edges.

Every relationship in the system lives here. Edges are typed, directed,
and stored in a tiny SQLite DB at runtime/records/_links.db so we can
query both directions cheaply.

Schema:
    record_links(
        src_kind  TEXT,
        src_id    TEXT,
        rel       TEXT,
        dst_kind  TEXT,
        dst_id    TEXT,
        created_at REAL,
        actor     TEXT,
        PRIMARY KEY(src_kind, src_id, rel, dst_kind, dst_id)
    )

Standard relations (extend freely — the DB does not enforce a vocabulary):
    relates_to     — soft, generic association
    mentions       — auto-extracted from text
    child_of       — hierarchy (step child_of project)
    promoted_from  — record was created by promoting another (ticket→proposal)
    promoted_to    — inverse of promoted_from (auto-written together)
    supersedes     — newer record replaces older
    superseded_by  — inverse of supersedes
    derived_from   — file/doc generated from another record
    attached_to    — attachment lives on this record
    blocks         — blocking dependency
    blocked_by     — inverse of blocks

Public API:
    link(src, rel, dst, actor='system')        — add an edge (idempotent)
    unlink(src, rel, dst)                      — remove an edge
    outgoing(kind, id) -> list[Edge]
    incoming(kind, id) -> list[Edge]
    neighbours(kind, id) -> {'outgoing': [...], 'incoming': [...]}
    all_links() -> iterator
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, asdict
from typing import Iterator, List, Optional, Tuple

from .store import LINKS_DB

# Inverse relations are written automatically so backlinks always work.
INVERSES = {
    "promoted_from": "promoted_to",
    "promoted_to":   "promoted_from",
    "supersedes":    "superseded_by",
    "superseded_by": "supersedes",
    "blocks":        "blocked_by",
    "blocked_by":    "blocks",
    "child_of":      "parent_of",
    "parent_of":     "child_of",
}


@dataclass
class Edge:
    src_kind: str
    src_id: str
    rel: str
    dst_kind: str
    dst_id: str
    created_at: float
    actor: str

    def as_dict(self) -> dict:
        return asdict(self)


def _conn() -> sqlite3.Connection:
    LINKS_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(LINKS_DB)
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE IF NOT EXISTS record_links ("
        " src_kind TEXT, src_id TEXT, rel TEXT,"
        " dst_kind TEXT, dst_id TEXT,"
        " created_at REAL, actor TEXT,"
        " PRIMARY KEY(src_kind, src_id, rel, dst_kind, dst_id))"
    )
    c.execute("CREATE INDEX IF NOT EXISTS ix_links_src ON record_links(src_kind, src_id)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_links_dst ON record_links(dst_kind, dst_id)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_links_rel ON record_links(rel)")
    return c


def link(
    src: Tuple[str, str],
    rel: str,
    dst: Tuple[str, str],
    *,
    actor: str = "system",
    write_inverse: bool = True,
) -> None:
    """Idempotent edge insert. Writes the inverse edge automatically when known."""
    sk, sid = src
    dk, did = dst
    now = time.time()
    c = _conn()
    try:
        c.execute(
            "INSERT OR IGNORE INTO record_links VALUES (?,?,?,?,?,?,?)",
            (sk, str(sid), rel, dk, str(did), now, actor),
        )
        if write_inverse and rel in INVERSES:
            c.execute(
                "INSERT OR IGNORE INTO record_links VALUES (?,?,?,?,?,?,?)",
                (dk, str(did), INVERSES[rel], sk, str(sid), now, actor),
            )
        c.commit()
    finally:
        c.close()


def unlink(src: Tuple[str, str], rel: str, dst: Tuple[str, str]) -> int:
    sk, sid = src
    dk, did = dst
    c = _conn()
    try:
        cur = c.execute(
            "DELETE FROM record_links WHERE src_kind=? AND src_id=? "
            "AND rel=? AND dst_kind=? AND dst_id=?",
            (sk, str(sid), rel, dk, str(did)),
        )
        # also remove the inverse if applicable
        if rel in INVERSES:
            c.execute(
                "DELETE FROM record_links WHERE src_kind=? AND src_id=? "
                "AND rel=? AND dst_kind=? AND dst_id=?",
                (dk, str(did), INVERSES[rel], sk, str(sid)),
            )
        c.commit()
        return cur.rowcount or 0
    finally:
        c.close()


def _row_to_edge(r: sqlite3.Row) -> Edge:
    return Edge(
        src_kind=r["src_kind"], src_id=r["src_id"], rel=r["rel"],
        dst_kind=r["dst_kind"], dst_id=r["dst_id"],
        created_at=r["created_at"], actor=r["actor"],
    )


def outgoing(kind: str, record_id: str) -> List[Edge]:
    c = _conn()
    try:
        return [_row_to_edge(r) for r in c.execute(
            "SELECT * FROM record_links WHERE src_kind=? AND src_id=? "
            "ORDER BY rel, created_at",
            (kind, str(record_id)),
        )]
    finally:
        c.close()


def incoming(kind: str, record_id: str) -> List[Edge]:
    c = _conn()
    try:
        return [_row_to_edge(r) for r in c.execute(
            "SELECT * FROM record_links WHERE dst_kind=? AND dst_id=? "
            "ORDER BY rel, created_at",
            (kind, str(record_id)),
        )]
    finally:
        c.close()


def neighbours(kind: str, record_id: str) -> dict:
    return {
        "outgoing": [e.as_dict() for e in outgoing(kind, record_id)],
        "incoming": [e.as_dict() for e in incoming(kind, record_id)],
    }


def all_links() -> Iterator[Edge]:
    c = _conn()
    try:
        for r in c.execute("SELECT * FROM record_links"):
            yield _row_to_edge(r)
    finally:
        c.close()


def count() -> int:
    c = _conn()
    try:
        return c.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
    finally:
        c.close()


__all__ = [
    "Edge", "INVERSES",
    "link", "unlink",
    "outgoing", "incoming", "neighbours", "all_links", "count",
]
