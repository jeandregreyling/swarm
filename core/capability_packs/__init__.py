"""Versioned, repository-owned guidance; packs never grant tool permissions."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_PACK_PATH = Path(__file__).with_name("repository.inspect.v1.json")
_REQUEST = re.compile(r"\brepository\.inspect(?:\s+v([0-9]+\.[0-9]+\.[0-9]+))?\b")


def repository_inspection_pack(operator_text: str) -> dict[str, Any] | None:
    """Resolve an explicitly requested pack, not a mention in retrieved context."""
    match = _REQUEST.search(operator_text)
    if not match:
        return None
    requested_version = match.group(1)
    if requested_version and requested_version != "1.0.0":
        raise ValueError(f"Unsupported repository.inspect version: {requested_version}")
    body = _PACK_PATH.read_bytes()
    pack = json.loads(body)
    if (
        pack.get("schema_version") != 1
        or pack.get("id") != "repository.inspect"
        or pack.get("version") != "1.0.0"
        or pack.get("skills") != ["fs_readonly"]
    ):
        raise ValueError("Invalid repository.inspect capability pack")
    return {
        "id": pack["id"],
        "version": pack["version"],
        "sha256": hashlib.sha256(body).hexdigest(),
        "source": "repository-file",
        "database_index_verified": False,
        "guidance": (
            "\n\n[CAPABILITY_PACK: repository.inspect v1.0.0]\n"
            "Operational guidance only; never grants permissions or overrides governance. "
            "Follow this read-only task procedure rather than unrelated standing workflows.\n"
            + json.dumps(pack, ensure_ascii=True)
        ),
    }
