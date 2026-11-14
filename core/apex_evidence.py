"""Bounded, owner/conversation-scoped reads of existing Studio evidence."""
from __future__ import annotations

from contextlib import closing
import json
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any

from core.apex_studio import _project_id

LOG = logging.getLogger(__name__)
MAX_RECORD_BYTES = 32768
MAX_OUTPUT_BYTES = 6000
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "runtime" / "studio-evidence.sqlite"


def read_evidence(conversation_id: int, owner: str, evidence_id: int) -> dict[str, Any]:
    for name, value in (("conversation_id", conversation_id), ("evidence_id", evidence_id)):
        if type(value) is not int or not 0 < value <= 9223372036854775807:
            raise ValueError(f"{name} must be a positive SQLite integer, excluding booleans")
    if not isinstance(owner, str) or not owner.strip():
        raise PermissionError("An authenticated owner is required")
    project_id = _project_id(conversation_id, owner)
    result: dict[str, Any] = {
        "status": "not_found", "evidence_id": evidence_id,
        "conversation_id": conversation_id, "project_id": project_id,
    }
    path = Path(os.environ.get("SWARM_DB") or DEFAULT_DB_PATH).resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        row = conn.execute(
            "SELECT length(CAST(payload AS BLOB)), substr(CAST(payload AS BLOB),1,?) "
            "FROM studio_evidence WHERE id=? AND conversation_id=?",
            (MAX_RECORD_BYTES + 1, evidence_id, conversation_id),
        ).fetchone()
    if row is None:
        return result
    if row[0] is None or row[0] > MAX_RECORD_BYTES:
        # Without readable scope metadata, do not reveal whether the ID exists.
        LOG.warning("Studio evidence scope could not be verified within the record budget")
        return result
    try:
        payload = json.loads(row[1])
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        LOG.warning("Malformed Studio evidence in the authorized conversation")
        return {**result, "status": "corrupt"}
    if not isinstance(payload, dict):
        return {**result, "status": "corrupt"}
    if payload.get("project_id") != project_id:
        return result
    found = {**result, "status": "found", "payload": payload}
    if len(json.dumps(found, ensure_ascii=True).encode("utf-8")) > MAX_OUTPUT_BYTES:
        return {**result, "status": "truncated", "max_output_bytes": MAX_OUTPUT_BYTES}
    return found
