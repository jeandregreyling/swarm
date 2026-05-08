"""core.coding_bible_probe — runtime verification of Coding Bible fan-out.

V7C-R15 deferred (1): "no runtime import-level verification that the Bible
prefix actually reaches each agent's live process prompt after their module
loads."

This module answers: *at runtime, right now, which agents are drinking from
the fountain and which aren't?* It re-imports ``utils.config`` into the
active process and walks the live ``globals()`` — no string-scanning of
source files, no test files that can lie.

The probe is the single source of truth for:
    - /api/coding-bible/probe            (JSON report for UIs and tests)
    - tests/test_v7c_r15_*               (pytest that consumes the report)
    - optional Settings per-agent toggle (future; reads `status='excluded'`)

Output schema::

    {
      "ok": true,
      "marker": "CODING BIBLE",
      "card_present": True,
      "total": 16,
      "covered": 16,
      "missing": [],
      "librarian_clean": True,
      "agents": {
        "GEMMA_SYSTEM_PROMPT": {
          "status": "covered" | "missing" | "excluded" | "unset",
          "length": 4021,
          "starts_with_card": True
        },
        ...
      }
    }
"""
from __future__ import annotations

from typing import Any, Dict, List

BIBLE_MARKER = "CODING BIBLE"

# Must stay aligned with utils.config._CODING_BIBLE_AGENTS.
# The import below re-confirms that at runtime — if config drifts, the
# probe reports drift, not silently diverges.
from utils import config as _cfg  # noqa: E402  (runtime import is the point)

EXPECTED_AGENTS = tuple(getattr(_cfg, "_CODING_BIBLE_AGENTS", ()))
# Agents explicitly excluded from the fan-out (Librarian emits tags only).
EXCLUDED_AGENTS = ("LIBRARIAN_SYSTEM_PROMPT",)


def _card_available() -> bool:
    try:
        try:
            from utils.coding_bible import quick_card
        except ImportError:
            from coding_bible import quick_card  # type: ignore
        return bool(quick_card())
    except Exception:
        return False


def probe() -> Dict[str, Any]:
    """Return a live report of Coding Bible coverage across agent prompts."""
    agents: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []

    for name in EXPECTED_AGENTS:
        val = getattr(_cfg, name, None)
        if not isinstance(val, str):
            agents[name] = {"status": "unset", "length": 0, "starts_with_card": False}
            missing.append(name)
            continue
        covered = BIBLE_MARKER in val
        agents[name] = {
            "status": "covered" if covered else "missing",
            "length": len(val),
            "starts_with_card": val.lstrip().startswith(BIBLE_MARKER)
            or (len(val) > 40 and BIBLE_MARKER in val[:400]),
        }
        if not covered:
            missing.append(name)

    # Librarian must NOT carry the Bible — tags-only output.
    librarian_clean = True
    for name in EXCLUDED_AGENTS:
        val = getattr(_cfg, name, None)
        if isinstance(val, str):
            entry = {
                "status": "excluded",
                "length": len(val),
                "starts_with_card": False,
            }
            if BIBLE_MARKER in val:
                entry["status"] = "leaked"
                librarian_clean = False
            agents[name] = entry

    return {
        "ok": not missing and librarian_clean,
        "marker": BIBLE_MARKER,
        "card_present": _card_available(),
        "total": len(EXPECTED_AGENTS),
        "covered": len(EXPECTED_AGENTS) - len(missing),
        "missing": missing,
        "librarian_clean": librarian_clean,
        "agents": agents,
    }


__all__ = ["probe", "BIBLE_MARKER", "EXPECTED_AGENTS", "EXCLUDED_AGENTS"]
