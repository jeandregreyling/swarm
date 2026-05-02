"""core.feeds — server-side feed subscription store + RSS fetcher.

V7C-A10 refinement. Feeds previously persisted only in ``localStorage``
so the swarm couldn't actually see them. This module gives them a home
in the main swarm DB and provides a minimal feedparser-less RSS fetcher
that returns item dicts suitable for the Library knowledge graph.

Tables::

    feed_subscriptions (
        sub_id      TEXT PRIMARY KEY,
        owner       TEXT,
        kind        TEXT,   -- 'rss' | 'atom' | 'x' | 'hn' | 'linkedin' | ...
        url         TEXT,
        title       TEXT,
        enabled     INTEGER DEFAULT 1,
        status      TEXT DEFAULT 'pending',  -- 'connected' | 'pending' | 'error'
        last_error  TEXT,
        last_poll   REAL,
        created_at  REAL
    )

The fetcher uses the stdlib only (``urllib`` + ``xml.etree.ElementTree``)
so there is no new third-party dependency. It returns up to ``limit``
items per feed with ``{title, link, summary, published}``.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

__all__ = [
    "ensure_schema", "list_subscriptions", "add_subscription",
    "remove_subscription", "update_subscription", "set_status",
    "fetch_rss", "poll_once", "KINDS", "STATUSES",
]

KINDS = (
    "rss", "atom", "x", "hn", "linkedin", "stackoverflow", "reddit",
    "github", "gmail", "youtube", "youtube-music", "spotify",
    "apple-music", "soundcloud", "bandcamp", "npm", "pypi",
)
STATUSES = ("connected", "pending", "error", "disabled")


def _conn() -> sqlite3.Connection:
    from utils.db._connection import get_connection
    return get_connection()


def ensure_schema() -> None:
    conn = _conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feed_subscriptions (
                sub_id     TEXT PRIMARY KEY,
                owner      TEXT NOT NULL DEFAULT 'seven',
                kind       TEXT NOT NULL,
                url        TEXT NOT NULL,
                title      TEXT,
                enabled    INTEGER NOT NULL DEFAULT 1,
                status     TEXT NOT NULL DEFAULT 'pending',
                last_error TEXT,
                last_poll  REAL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_feed_subs_owner ON feed_subscriptions(owner)"
        )
        # STEP-FEEDS-CONNECTORS-USER-LOGIN-KC-20260430 — additive migration.
        # Each sub now optionally tracks the auth shape, an opaque credential
        # id (resolves via core.secrets if/when wired), provenance (who added
        # it from which login), and a KC topic for routing into interests.
        for col, ddl in (
            ("auth_kind",         "ALTER TABLE feed_subscriptions ADD COLUMN auth_kind TEXT"),
            ("auth_cred_id",      "ALTER TABLE feed_subscriptions ADD COLUMN auth_cred_id TEXT"),
            ("added_by_user",     "ALTER TABLE feed_subscriptions ADD COLUMN added_by_user TEXT"),
            ("source_login",      "ALTER TABLE feed_subscriptions ADD COLUMN source_login TEXT"),
            ("kc_topic",          "ALTER TABLE feed_subscriptions ADD COLUMN kc_topic TEXT"),
            ("disconnect_url",    "ALTER TABLE feed_subscriptions ADD COLUMN disconnect_url TEXT"),
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                # Column already exists.
                pass
        conn.commit()
    finally:
        conn.close()


def list_subscriptions(owner: str = "seven") -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT sub_id, owner, kind, url, title, enabled, status, last_error, last_poll, created_at, "
            "auth_kind, auth_cred_id, added_by_user, source_login, kc_topic, disconnect_url "
            "FROM feed_subscriptions WHERE owner=? ORDER BY created_at DESC",
            (owner,),
        ).fetchall()
    finally:
        conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {}
        d["enabled"] = bool(d.get("enabled"))
        # Default auth_kind to 'none' so callers can rely on the field.
        if not d.get("auth_kind"):
            d["auth_kind"] = "none"
        out.append(d)
    return out


def add_subscription(
    kind: str, url: str, *, title: Optional[str] = None,
    owner: str = "seven", status: str = "pending",
) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    url = (url or "").strip()
    if not url:
        raise ValueError("url required")
    ensure_schema()
    sub_id = "F-" + uuid.uuid4().hex[:10].upper()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO feed_subscriptions "
            "(sub_id, owner, kind, url, title, enabled, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (sub_id, owner, kind, url, title, status, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    return sub_id


def remove_subscription(sub_id: str, owner: str = "seven") -> bool:
    ensure_schema()
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM feed_subscriptions WHERE sub_id=? AND owner=?",
            (sub_id, owner),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_subscription(
    sub_id: str, *, enabled: Optional[bool] = None,
    title: Optional[str] = None, owner: str = "seven",
    auth_kind: Optional[str] = None, auth_cred_id: Optional[str] = None,
    added_by_user: Optional[str] = None, source_login: Optional[str] = None,
    kc_topic: Optional[str] = None, disconnect_url: Optional[str] = None,
) -> bool:
    ensure_schema()
    sets: list[str] = []
    params: list[Any] = []
    if enabled is not None:
        sets.append("enabled=?")
        params.append(1 if enabled else 0)
    if title is not None:
        sets.append("title=?")
        params.append(title)
    # STEP-FEEDS-CONNECTORS-USER-LOGIN-KC-20260430 — login + provenance + KC.
    if auth_kind is not None:
        if auth_kind not in {"none", "basic", "bearer", "oauth"}:
            raise ValueError(f"unknown auth_kind: {auth_kind}")
        sets.append("auth_kind=?")
        params.append(auth_kind)
    if auth_cred_id is not None:
        sets.append("auth_cred_id=?")
        params.append(auth_cred_id or None)
    if added_by_user is not None:
        sets.append("added_by_user=?")
        params.append(added_by_user or None)
    if source_login is not None:
        sets.append("source_login=?")
        params.append(source_login or None)
    if kc_topic is not None:
        sets.append("kc_topic=?")
        params.append(kc_topic or None)
    if disconnect_url is not None:
        sets.append("disconnect_url=?")
        params.append(disconnect_url or None)
    if not sets:
        return False
    params.extend([sub_id, owner])
    conn = _conn()
    try:
        cur = conn.execute(
            f"UPDATE feed_subscriptions SET {', '.join(sets)} WHERE sub_id=? AND owner=?",
            params,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_status(
    sub_id: str, status: str, *, error: Optional[str] = None,
    owner: str = "seven",
) -> bool:
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    ensure_schema()
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE feed_subscriptions SET status=?, last_error=?, last_poll=? "
            "WHERE sub_id=? AND owner=?",
            (status, error, time.time(), sub_id, owner),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── RSS / Atom parsing (stdlib only) ───────────────────────────────────

_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _text(elem: Optional[ET.Element]) -> str:
    return (elem.text or "").strip() if elem is not None and elem.text else ""


def fetch_rss(url: str, *, limit: int = 20, timeout: float = 5.0) -> List[Dict[str, str]]:
    """Return a list of ``{title, link, summary, published}`` for an RSS
    or Atom feed. Raises :class:`URLError` on network failure."""
    req = Request(url, headers={"User-Agent": "seven-swarm-feeds/1.0"})
    with urlopen(req, timeout=timeout) as r:
        body = r.read()
    root = ET.fromstring(body)
    items: List[Dict[str, str]] = []
    # RSS 2.0
    for item in root.iter("item"):
        items.append({
            "title": _text(item.find("title")),
            "link": _text(item.find("link")),
            "summary": _text(item.find("description")),
            "published": _text(item.find("pubDate")),
        })
        if len(items) >= limit:
            break
    if items:
        return items
    # Atom
    for entry in root.iter(_ATOM_NS + "entry"):
        link_el = entry.find(_ATOM_NS + "link")
        href = link_el.get("href", "") if link_el is not None else ""
        items.append({
            "title": _text(entry.find(_ATOM_NS + "title")),
            "link": href,
            "summary": _text(entry.find(_ATOM_NS + "summary")),
            "published": _text(entry.find(_ATOM_NS + "updated"))
                        or _text(entry.find(_ATOM_NS + "published")),
        })
        if len(items) >= limit:
            break
    return items


def poll_once(sub_id: str, *, owner: str = "seven", limit: int = 20) -> Dict[str, Any]:
    """Fetch a single subscription and update its status + last_poll."""
    ensure_schema()
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT kind, url FROM feed_subscriptions WHERE sub_id=? AND owner=?",
            (sub_id, owner),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": "subscription not found"}
    kind = row[0] if not hasattr(row, "keys") else row["kind"]
    url = row[1] if not hasattr(row, "keys") else row["url"]
    if kind not in ("rss", "atom"):
        # OAuth connectors are out of scope for the first honest ship —
        # mark status explicitly so the UI can render "pending connector".
        set_status(sub_id, "pending", error=f"connector for {kind} not implemented",
                   owner=owner)
        return {"ok": False, "error": f"connector for {kind} not implemented",
                "kind": kind}
    try:
        items = fetch_rss(url, limit=limit)
        set_status(sub_id, "connected", error=None, owner=owner)
        return {"ok": True, "kind": kind, "count": len(items), "items": items}
    except (URLError, ET.ParseError, ValueError) as e:
        set_status(sub_id, "error", error=str(e), owner=owner)
        return {"ok": False, "error": str(e), "kind": kind}
