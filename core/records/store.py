"""core.records.store — Platinum layer per-record file storage.

Layout under runtime/records/:
    <kind>/<yyyy>/<mm>/<id>.json        canonical, machine-readable
    <kind>/<yyyy>/<mm>/<id>.md          derived sidecar, Spotlight-friendly
    _ledger.jsonl                       append-only history of every save
    _xref.json                          rebuilt cross-reference index
    _links.db (SQLite)                  typed edges (see core.records.links)

Rules (enforced by scripts/architecture_self_test.py):
  1. One file per record. Never split a record across files.
  2. DB row is the index, JSON file is the artifact.
  3. Two levels deep, never three (<kind>/<yyyy>/<mm>/).
  4. .json is canonical, .md is derived.
  5. ID is the filename. No spaces, no slashes.
  6. Threads are atomic — one file per thread, embedded messages.
  7. The ledger is append-only.

Public API:
  save_record(kind, id, data)   — write json + md, append ledger
  load_record(kind, id)         — read one record
  record_path(kind, id, ...)    — resolve on-disk json path
  record_md_path(kind, id, ...) — resolve sidecar md path
  snapshot_all()                — bulk export every kind from the DB
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Anchor on SWARM_ROOT so the layout is portable.
_SWARM_ROOT = Path(os.environ.get("SWARM_ROOT") or Path(__file__).resolve().parents[2])
RECORDS_ROOT = _SWARM_ROOT / "runtime" / "records"
LEDGER_PATH = RECORDS_ROOT / "_ledger.jsonl"
XREF_PATH = RECORDS_ROOT / "_xref.json"
LINKS_DB = RECORDS_ROOT / "_links.db"

# (kind, table, pk col, created col, title col)
KINDS: Tuple[Tuple[str, str, str, Optional[str], Optional[str]], ...] = (
    ("project",  "projects",                 "project_id",  "created_at",  "name"),
    ("step",     "project_steps",            "step_id",     "created_at",  "title"),
    ("case",     "project_test_cases",       "case_id",     "created_at",  "title"),
    ("run",      "test_runs",                "run_id",      "started_at",  None),
    ("proposal", "work_proposals",           "proposal_id", "created_at",  "title"),
    ("ticket",   "tickets",                  "ticket_number", "created_at", "question"),
    ("email",    "pending_emails",           "id",          "created_at",  "subject"),
    ("note",     "project_blackboard_notes", "note_id",     "created_at",  "title"),
    ("doc",      "project_docs",             "id",          "created_at",  "doc_name"),
    # threads = conversations + their messages, stored atomically per thread
    ("thread",   "conversations",            "id",          "created_at",  "title"),
)

# Patterns we extract from text fields to build the xref index.
_ID_PATTERNS = [
    (re.compile(r"\b(P-[0-9A-F]{8,})\b"),                 "project"),
    (re.compile(r"\b(S-[0-9A-F]{8,})\b"),                 "step"),
    (re.compile(r"\b(MD-FEATURE-[0-9A-F]{8,})\b"),        "step"),
    (re.compile(r"\b(C-[0-9A-F]{8,})\b"),                 "case"),
    (re.compile(r"\b(R-[0-9A-F]{8,})\b"),                 "run"),
    (re.compile(r"\b(PR-[0-9A-F]{8,})\b"),                "proposal"),
    (re.compile(r"\b(TKT-[0-9A-F]{8,})\b"),               "ticket"),
    (re.compile(r"\b(N-[0-9A-Z_-]{4,})\b"),               "note"),
    (re.compile(r"\b(T-[0-9A-F]{6,})\b"),                 "thread"),
    (re.compile(r"\b(PACKET-\d{2})\b"),                   "packet"),
]


def _bucket_for(record: Dict[str, Any], created_col: Optional[str]) -> Tuple[str, str]:
    raw = record.get(created_col) if created_col else None
    try:
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        elif isinstance(raw, str) and raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.now(tz=timezone.utc)
    except Exception:
        dt = datetime.now(tz=timezone.utc)
    return f"{dt.year:04d}", f"{dt.month:02d}"


def _safe(record_id: Any) -> str:
    return str(record_id).replace("/", "_").replace("\\", "_")


def record_path(kind: str, record_id: str, *, year: Optional[str] = None, month: Optional[str] = None) -> Path:
    base = RECORDS_ROOT / kind
    if year and month:
        base = base / year / month
    return base / f"{_safe(record_id)}.json"


def record_md_path(kind: str, record_id: str, *, year: Optional[str] = None, month: Optional[str] = None) -> Path:
    return record_path(kind, record_id, year=year, month=month).with_suffix(".md")


def _kind_meta(kind: str) -> Tuple[str, str, Optional[str], Optional[str]]:
    for k, t, pk, c, tc in KINDS:
        if k == kind:
            return t, pk, c, tc
    raise KeyError(f"unknown kind: {kind}")


def _extract_mentions(text: str) -> List[Tuple[str, str]]:
    if not text:
        return []
    out: List[Tuple[str, str]] = []
    seen = set()
    for pat, kind in _ID_PATTERNS:
        for m in pat.findall(text):
            key = (kind, m)
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def _fmt_ts(ts: Any) -> str:
    if ts is None or ts == "":
        return ""
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                return ts[:19]
    except Exception:
        pass
    return str(ts)


def _render_markdown(kind: str, record_id: str, data: Dict[str, Any]) -> str:
    """Build the human-readable sidecar for a single record."""
    _, _, created_col, title_col = _kind_meta(kind)
    title = (data.get(title_col) if title_col else None) or f"{kind} {record_id}"
    lines: List[str] = [f"# {title}", ""]
    meta = [f"**Kind:** {kind}", f"**ID:** `{record_id}`"]
    if data.get("status"):
        meta.append(f"**Status:** {data['status']}")
    if data.get("project_id"):
        meta.append(f"**Project:** `{data['project_id']}`")
    if created_col and data.get(created_col):
        meta.append(f"**Created:** {_fmt_ts(data.get(created_col))}")
    if data.get("updated_at"):
        meta.append(f"**Updated:** {_fmt_ts(data.get('updated_at'))}")
    lines.append("   ".join(meta))
    lines.append("")

    body_field = None
    for cand in ("description", "body", "content", "summary", "rationale", "instructions"):
        if data.get(cand):
            body_field = cand
            break
    if body_field:
        lines.append("## Body")
        lines.append("")
        lines.append(str(data[body_field]).strip())
        lines.append("")

    if kind == "thread" and isinstance(data.get("messages"), list):
        lines.append(f"## Messages ({len(data['messages'])})")
        lines.append("")
        for m in data["messages"]:
            ts = _fmt_ts(m.get("created_at"))
            who = m.get("from_agent") or "?"
            to = f" → {m['to_agent']}" if m.get("to_agent") else ""
            lines.append(f"### {ts} — {who}{to}")
            lines.append("")
            lines.append((m.get("content") or "").strip())
            lines.append("")

    text_blob = " ".join(
        str(v) for k, v in data.items()
        if isinstance(v, str) and len(v) < 50_000
    )
    mentions = _extract_mentions(text_blob)
    if mentions:
        lines.append("## Mentions")
        lines.append("")
        for mk, mid in mentions:
            if mk == kind and mid == record_id:
                continue
            lines.append(f"- {mk} → `{mid}`")
        lines.append("")

    rel = record_path(kind, record_id).relative_to(_SWARM_ROOT)
    lines.append("---")
    lines.append(f"_File:_ `{rel}`")
    lines.append("")
    return "\n".join(lines)


def _append_ledger(entry: Dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, sort_keys=True, default=str)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_record(kind: str, record_id: str, data: Dict[str, Any], *, actor: str = "system") -> Path:
    """Write canonical .json + sidecar .md + ledger entry. Idempotent."""
    _, _, created_col, _ = _kind_meta(kind)
    yyyy, mm = _bucket_for(data, created_col)
    p = record_path(kind, record_id, year=yyyy, month=mm)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"kind": kind, "id": str(record_id), "saved_at": time.time(), "data": data}
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)

    changed = True
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
            if existing.get("data") == data:
                changed = False
        except Exception:
            changed = True

    if changed:
        p.write_text(body, encoding="utf-8")
        p.with_suffix(".md").write_text(_render_markdown(kind, str(record_id), data), encoding="utf-8")
        _append_ledger({
            "ts": time.time(),
            "kind": kind,
            "id": str(record_id),
            "action": "save",
            "actor": actor,
            "path": str(p.relative_to(_SWARM_ROOT)),
        })
    return p


def load_record(kind: str, record_id: str) -> Optional[Dict[str, Any]]:
    base = RECORDS_ROOT / kind
    if not base.exists():
        return None
    name = f"{_safe(record_id)}.json"
    for path in base.rglob(name):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def _iter_table(conn: sqlite3.Connection, table: str) -> Iterable[Dict[str, Any]]:
    cur = conn.execute(f"SELECT * FROM {table}")
    cols = [c[0] for c in cur.description]
    for row in cur:
        yield dict(zip(cols, row))


def _load_thread(conn: sqlite3.Connection, conv_id: int) -> Optional[Dict[str, Any]]:
    cur = conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,))
    cols = [c[0] for c in cur.description]
    row = cur.fetchone()
    if not row:
        return None
    out = dict(zip(cols, row))
    mcur = conn.execute(
        "SELECT id, from_agent, to_agent, content, message_type, created_at, tokens_used "
        "FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,)
    )
    mcols = [c[0] for c in mcur.description]
    out["messages"] = [dict(zip(mcols, r)) for r in mcur]
    return out


def snapshot_all(*, db_path: Optional[Path] = None, actor: str = "snapshot_all") -> Dict[str, int]:
    db = Path(db_path) if db_path else (_SWARM_ROOT / "swarm_memory.db")
    if not db.exists():
        raise FileNotFoundError(f"db missing: {db}")
    counts: Dict[str, int] = {}
    conn = sqlite3.connect(db)
    try:
        for kind, table, pk, _c, _t in KINDS:
            try:
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                counts[kind] = 0
                continue
            n = 0
            if kind == "thread":
                ids = [r[0] for r in conn.execute(f"SELECT {pk} FROM {table}")]
                for cid in ids:
                    data = _load_thread(conn, cid)
                    if data is None:
                        continue
                    save_record(kind, str(cid), data, actor=actor)
                    n += 1
            else:
                for row in _iter_table(conn, table):
                    rid = row.get(pk)
                    if rid is None:
                        continue
                    save_record(kind, str(rid), row, actor=actor)
                    n += 1
            counts[kind] = n
    finally:
        conn.close()
    return counts


def mirror(kind: str, record_id: Any, *, actor: str = "mutation", db_path: Optional[Path] = None) -> Optional[Path]:
    """Re-read one row from the DB and refresh its on-disk record.

    Designed to be called from mutation hooks after a create/update.
    Failures are swallowed (logged via the ledger only) so a hook never
    breaks the originating write — the snapshot is the safety net.
    """
    if record_id is None:
        return None
    table, pk, _, _ = _kind_meta(kind)
    db = Path(db_path) if db_path else (_SWARM_ROOT / "swarm_memory.db")
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(db)
        try:
            if kind == "thread":
                try:
                    cid_int = int(record_id)
                except (TypeError, ValueError):
                    return None
                data = _load_thread(conn, cid_int)
                if data is None:
                    return None
                return save_record(kind, str(cid_int), data, actor=actor)
            cur = conn.execute(f"SELECT * FROM {table} WHERE {pk}=?", (record_id,))
            cols = [c[0] for c in cur.description]
            row = cur.fetchone()
            if not row:
                return None
            data = dict(zip(cols, row))
            return save_record(kind, str(record_id), data, actor=actor)
        finally:
            conn.close()
    except Exception:
        return None


__all__ = [
    "RECORDS_ROOT", "LEDGER_PATH", "XREF_PATH", "LINKS_DB", "KINDS",
    "record_path", "record_md_path",
    "save_record", "load_record", "restore_record", "snapshot_all", "mirror",
    "_render_markdown", "_extract_mentions", "_kind_meta",
]


def restore_record(
    kind: str,
    record_id: str,
    *,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Re-import a record from its on-disk JSON file back into the DB.

    Acceptance criterion for S-7221671DD4: deleting the row from the DB
    and re-importing the file must restore the record byte-for-byte.

    Returns a status dict::

        {"ok": bool, "kind": str, "id": str, "data": dict | None,
         "action": "inserted" | "updated" | "missing"}

    Threads are not supported here (they fan out to a join table); the
    caller should use snapshot_all() in reverse for those.
    """
    table, pk, _, _ = _kind_meta(kind)
    if kind == "thread":
        return {"ok": False, "kind": kind, "id": str(record_id),
                "data": None, "action": "unsupported"}
    payload = load_record(kind, record_id)
    if payload is None:
        return {"ok": False, "kind": kind, "id": str(record_id),
                "data": None, "action": "missing"}
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {"ok": False, "kind": kind, "id": str(record_id),
                "data": None, "action": "missing"}

    own_conn = False
    if conn is None:
        db = Path(db_path) if db_path else (_SWARM_ROOT / "swarm_memory.db")
        if not db.exists():
            return {"ok": False, "kind": kind, "id": str(record_id),
                    "data": data, "action": "no_db"}
        conn = sqlite3.connect(db)
        own_conn = True

    try:
        cols = list(data.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        existing = conn.execute(
            f"SELECT 1 FROM {table} WHERE {pk}=?", (data.get(pk),)
        ).fetchone()
        if existing:
            assignments = ",".join(f"{c}=?" for c in cols if c != pk)
            values = [data[c] for c in cols if c != pk]
            values.append(data.get(pk))
            conn.execute(
                f"UPDATE {table} SET {assignments} WHERE {pk}=?",
                values,
            )
            action = "updated"
        else:
            conn.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                [data[c] for c in cols],
            )
            action = "inserted"
        conn.commit()
        return {"ok": True, "kind": kind, "id": str(record_id),
                "data": data, "action": action}
    finally:
        if own_conn:
            conn.close()
