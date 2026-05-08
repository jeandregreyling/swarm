"""core.records.promote — Platinum layer record morphing.

A ticket can become a proposal, a proposal can become a project, a chat
thread can become a ticket. Promotion writes a new record AND a typed
edge (`promoted_from` on the new, `promoted_to` on the old) so the
neurological matrix knows how the items relate forever.

This module deliberately does not duplicate the ID-generation logic of
core.knowledge.projects — it imports those creators where they exist.
For kinds that do not yet have a public creator, we generate a stable
ID and write the row directly.

Public API:
    promote(src_kind, src_id, dst_kind, **overrides) -> (dst_kind, dst_id)
    promotion_chain(kind, id) -> [(kind, id), ...]   walk the chain
"""
from __future__ import annotations

import secrets
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .store import _SWARM_ROOT, _kind_meta, load_record, save_record
from .links import link, outgoing, incoming

DB = _SWARM_ROOT / "swarm_memory.db"

# How fields flow when promoting from one kind to another.
# Each entry: (src_field, dst_field). Missing fields are skipped.
FIELD_MAP: Dict[Tuple[str, str], List[Tuple[str, str]]] = {
    ("ticket",   "proposal"): [("title", "title"), ("description", "rationale"), ("status", "status")],
    ("proposal", "project"):  [("title", "name"), ("rationale", "description")],
    ("ticket",   "project"):  [("title", "name"), ("description", "description")],
    ("thread",   "ticket"):   [("title", "title")],
    ("thread",   "proposal"): [("title", "title")],
    ("note",     "ticket"):   [("title", "title"), ("body", "description")],
    ("email",    "ticket"):   [("subject", "title"), ("body", "description")],
    ("step",     "ticket"):   [("title", "title"), ("description", "description")],
}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(5).upper()}"


def _id_prefix_for(kind: str) -> str:
    return {
        "project": "P",
        "step": "S",
        "case": "C",
        "run": "R",
        "proposal": "PR",
        "ticket": "TKT",
        "note": "N",
    }.get(kind, kind.upper()[:3])


def _create_destination(dst_kind: str, fields: dict) -> str:
    """Insert a new row of dst_kind directly. Returns the new id."""
    table, pk, _, _ = _kind_meta(dst_kind)
    # Generate a new ID unless a numeric pk (rare — email, doc).
    if pk in ("id",):
        # numeric autoincrement table
        new_id = None
    else:
        new_id = fields.get(pk) or _new_id(_id_prefix_for(dst_kind))
        fields = {**fields, pk: new_id}

    fields.setdefault("created_at", time.time())
    fields.setdefault("updated_at", time.time())

    # Kind-specific NOT NULL backfills so promote works on real schemas.
    if dst_kind == "ticket":
        fields.setdefault("ticket_number", _new_id("TKT"))
        fields.setdefault("sender_email", "system@swarm.local")
        fields.setdefault("question", fields.get("title") or fields.get("description") or "(promoted)")
    elif dst_kind == "proposal":
        fields.setdefault("agent", fields.get("actor") or "system")
        fields.setdefault("title", fields.get("title") or fields.get("question") or "(promoted)")
    elif dst_kind == "project":
        fields.setdefault("name", fields.get("title") or fields.get("question") or "(promoted)")
        # projects.created_at is REAL NOT NULL
        if not isinstance(fields.get("created_at"), (int, float)):
            fields["created_at"] = time.time()

    cols = list(fields.keys())
    conn = sqlite3.connect(DB)
    try:
        cur = conn.cursor()
        # Discover real columns to avoid OperationalError on extras.
        real = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        keep = [c for c in cols if c in real]
        if not keep:
            raise RuntimeError(f"no usable columns for {dst_kind}")
        vals = [fields[c] for c in keep]
        sql = f"INSERT INTO {table} ({','.join(keep)}) VALUES ({','.join('?' for _ in keep)})"
        cur.execute(sql, vals)
        conn.commit()
        if new_id is None:
            new_id = str(cur.lastrowid)
        # For tickets the canonical id we want to expose is ticket_number, not the integer pk.
        if dst_kind == "ticket":
            new_id = fields["ticket_number"]
        return str(new_id)
    finally:
        conn.close()


def _fetch_row(kind: str, record_id: str) -> Optional[dict]:
    table, pk, _, _ = _kind_meta(kind)
    conn = sqlite3.connect(DB)
    try:
        cur = conn.execute(f"SELECT * FROM {table} WHERE {pk}=?", (record_id,))
        cols = [c[0] for c in cur.description]
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip(cols, row))
    finally:
        conn.close()


def promote(
    src_kind: str,
    src_id: str,
    dst_kind: str,
    *,
    overrides: Optional[dict] = None,
    actor: str = "promote",
) -> Tuple[str, str]:
    """Create a new record of dst_kind from src, write the typed edges,
    and refresh both records on disk. Returns (dst_kind, dst_id)."""
    src_row = _fetch_row(src_kind, src_id)
    if src_row is None:
        raise KeyError(f"{src_kind} {src_id} not found")

    mapping = FIELD_MAP.get((src_kind, dst_kind), [])
    fields: dict = {}
    for s_field, d_field in mapping:
        if src_row.get(s_field) is not None:
            fields[d_field] = src_row[s_field]
    if overrides:
        fields.update(overrides)

    # Sensible defaults the destination kind probably wants.
    if dst_kind in ("ticket", "proposal", "step", "case") and "status" not in fields:
        fields["status"] = "todo"

    new_id = _create_destination(dst_kind, fields)

    # Refresh both records to disk so the per-record file store stays current.
    new_row = _fetch_row(dst_kind, new_id) or fields
    save_record(dst_kind, new_id, new_row, actor=actor)
    fresh_src = _fetch_row(src_kind, src_id)
    if fresh_src:
        save_record(src_kind, src_id, fresh_src, actor=actor)

    # The Platinum edges — both directions written automatically by INVERSES.
    link((dst_kind, new_id), "promoted_from", (src_kind, src_id), actor=actor)
    return dst_kind, new_id


def promotion_chain(kind: str, record_id: str) -> List[Tuple[str, str]]:
    """Walk promoted_from edges backwards to the origin and forward to leaves."""
    chain: List[Tuple[str, str]] = [(kind, str(record_id))]

    # Walk upstream (older).
    current = (kind, str(record_id))
    seen = {current}
    while True:
        out = [e for e in outgoing(*current) if e.rel == "promoted_from"]
        if not out:
            break
        nxt = (out[0].dst_kind, out[0].dst_id)
        if nxt in seen:
            break
        chain.insert(0, nxt)
        seen.add(nxt)
        current = nxt

    # Walk downstream (newer).
    current = (kind, str(record_id))
    while True:
        out = [e for e in outgoing(*current) if e.rel == "promoted_to"]
        if not out:
            break
        nxt = (out[0].dst_kind, out[0].dst_id)
        if nxt in seen:
            break
        chain.append(nxt)
        seen.add(nxt)
        current = nxt

    return chain


__all__ = ["promote", "promotion_chain", "FIELD_MAP"]
