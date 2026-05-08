"""ops/kc_seeds/_loader.py — declarative KC seed pipeline.

Walks ``ops/kc_seeds/*.yaml``, validates each file, and returns structured
topic records ready to be written to the Knowledge Centre database. Keeping
the loader separate from the DB layer lets tests exercise validation without
spinning up the full app.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


SEED_DIR = pathlib.Path(__file__).resolve().parent
VALID_CADENCES = {"daily", "weekly", "monthly", "manual"}
VALID_SOURCE_KINDS = {"url", "file", "prompt", "repo"}


@dataclass
class SeedSource:
    kind: str
    url: Optional[str] = None
    path: Optional[str] = None
    text: Optional[str] = None
    title: Optional[str] = None
    selector: Optional[str] = None


@dataclass
class SeedTopic:
    topic_id: str
    title: str
    cadence: str = "manual"
    tags: list[str] = field(default_factory=list)
    sources: list[SeedSource] = field(default_factory=list)
    path: Optional[str] = None

    @property
    def errors(self) -> list[str]:
        errs: list[str] = []
        if not self.topic_id:
            errs.append("topic_id required")
        if self.cadence not in VALID_CADENCES:
            errs.append(f"cadence '{self.cadence}' invalid")
        for i, src in enumerate(self.sources):
            if src.kind not in VALID_SOURCE_KINDS:
                errs.append(f"sources[{i}].kind '{src.kind}' invalid")
            if src.kind == "url" and not src.url:
                errs.append(f"sources[{i}].url required")
            if src.kind == "file" and not src.path:
                errs.append(f"sources[{i}].path required")
            if src.kind == "prompt" and not src.text:
                errs.append(f"sources[{i}].text required")
        return errs


def _parse(path: pathlib.Path) -> Optional[SeedTopic]:
    if not yaml:
        return None
    try:
        with path.open() as fh:
            raw = yaml.safe_load(fh) or {}
    except OSError:
        return None
    sources = [SeedSource(**s) for s in (raw.get("sources") or [])]
    topic = SeedTopic(
        topic_id=str(raw.get("topic_id") or ""),
        title=str(raw.get("title") or ""),
        cadence=str(raw.get("cadence") or "manual"),
        tags=list(raw.get("tags") or []),
        sources=sources,
        path=str(path),
    )
    return topic


def load_all(root: Optional[pathlib.Path] = None) -> list[SeedTopic]:
    root = root or SEED_DIR
    topics: list[SeedTopic] = []
    for yml in sorted(root.glob("*.yaml")):
        topic = _parse(yml)
        if topic:
            topics.append(topic)
    return topics


def validate_all(root: Optional[pathlib.Path] = None) -> dict[str, list[str]]:
    return {t.topic_id or str(t.path): t.errors for t in load_all(root)}
