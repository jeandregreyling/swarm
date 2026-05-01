"""core.records.xref — Platinum layer cross-reference builder.

Scans every record on disk for ID-pattern mentions (P-..., S-..., TKT-...,
PACKET-...) and writes them as `mentions` edges in the links DB plus a
denormalised _xref.json index for the UI.

Run after a snapshot to refresh: `python3 -m core.records.xref`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List

from .links import _conn, link
from .store import RECORDS_ROOT, XREF_PATH, KINDS, _extract_mentions


def build() -> Dict[str, int]:
    """Walk runtime/records/<kind>/**/*.json, extract mentions, persist edges,
    and write _xref.json. Returns counts: {records, edges, mentions}."""
    edge_count = 0
    record_count = 0
    xref: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: {"incoming": [], "outgoing": []})

    # Reset the mentions edges only — keep manual links untouched.
    c = _conn()
    try:
        c.execute("DELETE FROM record_links WHERE rel='mentions' OR rel='mentioned_by'")
        c.commit()
    finally:
        c.close()

    for kind, *_ in KINDS:
        kind_dir = RECORDS_ROOT / kind
        if not kind_dir.exists():
            continue
        for path in kind_dir.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            data = payload.get("data") or {}
            rid = payload.get("id") or ""
            if not rid:
                continue
            record_count += 1

            # Threads include messages — flatten content for mention scanning.
            text_parts = [str(v) for v in data.values() if isinstance(v, str)]
            if kind == "thread" and isinstance(data.get("messages"), list):
                text_parts.extend(
                    str(m.get("content") or "") for m in data["messages"]
                )
            blob = " ".join(text_parts)
            mentions = _extract_mentions(blob)

            src_key = f"{kind}:{rid}"
            for mk, mid in mentions:
                if mk == kind and mid == rid:
                    continue
                if mk == "packet":
                    # packets are conceptual — skip edge, will live in xref only
                    xref[src_key]["outgoing"].append(f"{mk}:{mid}")
                    xref[f"{mk}:{mid}"]["incoming"].append(src_key)
                    continue
                link((kind, rid), "mentions", (mk, mid), actor="xref",
                     write_inverse=False)
                # write the inverse manually as 'mentioned_by' so we can
                # distinguish from manual links
                c2 = _conn()
                try:
                    c2.execute(
                        "INSERT OR IGNORE INTO record_links VALUES (?,?,?,?,?,?,?)",
                        (mk, mid, "mentioned_by", kind, rid, 0.0, "xref"),
                    )
                    c2.commit()
                finally:
                    c2.close()
                edge_count += 2
                xref[src_key]["outgoing"].append(f"{mk}:{mid}")
                xref[f"{mk}:{mid}"]["incoming"].append(src_key)

    XREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    XREF_PATH.write_text(
        json.dumps({k: v for k, v in xref.items()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {"records": record_count, "edges": edge_count, "xref_keys": len(xref)}


if __name__ == "__main__":
    out = build()
    print(json.dumps(out, indent=2))
