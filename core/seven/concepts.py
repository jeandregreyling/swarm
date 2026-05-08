"""core.seven.concepts — load Seven's self-knowledge from ``docs/seven/*.md``.

Each markdown file in ``docs/seven/`` becomes one row in
``seven_concepts``. Optional YAML-ish front-matter is supported but
unnecessary; the loader uses safe defaults if absent.

Front-matter (optional)::

    ---
    slug: perception
    title: Seven's Perception Layer
    tags: api, graph, observe
    ---

    # Body markdown follows…

If front-matter is missing, slug = filename stem (digit-prefixes stripped),
title = first ``# Heading`` or filename, tags = ``[]``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.records.store import _SWARM_ROOT  # type: ignore
from . import memory as _mem

SEVEN_DOCS = Path(_SWARM_ROOT) / "docs" / "seven"

_FRONT_RX = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_DIGIT_PREFIX_RX = re.compile(r"^\d+[-_]")


def _parse_front_matter(text: str) -> Tuple[Dict[str, str], str]:
    m = _FRONT_RX.match(text)
    if not m:
        return {}, text
    head = m.group(1)
    body = text[m.end():]
    fields: Dict[str, str] = {}
    for line in head.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fields[k.strip()] = v.strip()
    return fields, body


def _first_heading(md: str) -> Optional[str]:
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return None


def load_file(path: Path) -> Optional[Dict[str, str]]:
    if not path.is_file() or path.suffix.lower() != ".md":
        return None
    text = path.read_text(encoding="utf-8")
    fm, body = _parse_front_matter(text)
    stem = path.stem
    slug = fm.get("slug") or _DIGIT_PREFIX_RX.sub("", stem)
    title = fm.get("title") or _first_heading(body) or stem.replace("-", " ").title()
    tags = [t.strip() for t in (fm.get("tags") or "").split(",") if t.strip()]
    rel = str(path.relative_to(_SWARM_ROOT)) if path.is_absolute() else str(path)
    _mem.upsert_concept(slug=slug, title=title, body_md=body.strip(), tags=tags, source_path=rel)
    return {"slug": slug, "title": title, "source_path": rel, "tags": ",".join(tags)}


def reload_all() -> List[Dict[str, str]]:
    """Re-ingest every ``docs/seven/*.md`` file into ``seven_concepts``."""
    SEVEN_DOCS.mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, str]] = []
    for p in sorted(SEVEN_DOCS.glob("*.md")):
        rec = load_file(p)
        if rec:
            out.append(rec)
    return out


def ensure_seeded() -> int:
    """If Seven has *no* concepts yet, load them from disk. Returns count."""
    stats = _mem.memory_stats()
    if int(stats.get("concepts") or 0) == 0:
        return len(reload_all())
    return int(stats["concepts"])
