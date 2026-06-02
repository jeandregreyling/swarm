#!/usr/bin/env python3
"""Check that Ollama is serving the expected shared model store."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.db._connection import get_connection  # noqa: E402
from utils.ollama_model_guard import build_model_store_guard  # noqa: E402


def _ollama_models() -> set[str]:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as resp:
        payload = json.loads(resp.read().decode("utf-8") or "{}")
    return {
        str(item.get("model") or item.get("name") or "").strip().lower()
        for item in payload.get("models") or []
        if str(item.get("model") or item.get("name") or "").strip()
    }


def _agent_rows() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, model, tier, enabled FROM agents WHERE number >= 0 ORDER BY number ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def main() -> int:
    guard = build_model_store_guard(_agent_rows(), _ollama_models())
    print(json.dumps(guard, indent=2, sort_keys=True))
    if not guard["ok"]:
        return 2
    if guard["absent_from_expected"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
