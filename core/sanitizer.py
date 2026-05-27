"""
DOES Sanitizer — pipe-joint insulation for quantized model output.

Hardens the boundary between local LLM stdout and the SQL state engine.
Small quantized models (Qwen 1.5B / Gemma 4B INT4) leak:
  - markdown fences (```lang ... ```)
  - chatty preambles ("Sure, here is...", "Of course!", "Certainly!")
  - trailing commentary ("Let me know if...", "Hope this helps")
  - escape sequences, BOMs, zero-width chars
  - JSON wrapped in prose

Two surfaces:
  scrub_structural(text)  -> raw code/SQL/text safe for does_state.payload
  scrub_json(text)        -> parsed dict safe for does_audit.* columns
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Dict, Optional

# -- compiled patterns -------------------------------------------------------

_FENCE_BLOCK = re.compile(
    r"```(?:[a-zA-Z0-9_+\-]*)?\s*\n?(.*?)```",
    re.DOTALL,
)
_INLINE_FENCE = re.compile(r"`([^`\n]+)`")
_BOM = re.compile(r"[\ufeff\u200b-\u200f\u2060]")
_CR = re.compile(r"\r\n?")

# Conversational openers — anchored at start of line, case-insensitive.
_PREAMBLE = re.compile(
    r"""^\s*(?:
        sure[, ]|
        certainly[, ]|
        of\s+course[, ]|
        absolutely[, ]|
        here(?:'s|\s+is|\s+are|\s+you\s+go)\b|
        below\s+(?:is|are)\b|
        let\s+me\b|
        i\s+(?:will|'ll|can|have)\b|
        i'?m\s+going\s+to\b|
        the\s+following\b|
        as\s+(?:an?\s+)?(?:ai|assistant|requested)\b|
        okay[, ]|ok[, ]|alright[, ]
    )[^\n]*\n?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Trailing commentary — anchored at end-of-text.
_POSTAMBLE = re.compile(
    r"""\n+\s*(?:
        let\s+me\s+know[^\n]*|
        hope\s+(?:this|that)[^\n]*|
        feel\s+free[^\n]*|
        if\s+you\s+(?:have|need)[^\n]*|
        is\s+there\s+anything[^\n]*|
        note\s*:[^\n]*|
        explanation\s*:[^\n]*
    )\s*$""",
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

# Balanced JSON object extractor (greedy outer braces with brace counting).
def _extract_balanced_json(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


# -- public API --------------------------------------------------------------

def scrub_structural(text: str) -> str:
    """
    Return raw structural payload (code/SQL/plain text) with all conversational
    wrappers, markdown fences, BOMs, and CR padding stripped. Idempotent.
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text)
    s = _BOM.sub("", s)
    s = _CR.sub("\n", s)

    # Unwrap the FIRST fenced block if the model wrapped its answer.
    m = _FENCE_BLOCK.search(s)
    if m:
        s = m.group(1)
    else:
        # No fences — strip any stray inline backticks.
        s = _INLINE_FENCE.sub(r"\1", s)

    # Peel preambles (may stack).
    while True:
        new = _PREAMBLE.sub("", s, count=1)
        if new == s:
            break
        s = new

    s = _POSTAMBLE.sub("", s)
    return s.strip()


def scrub_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract and parse a single JSON object from noisy model output.
    Returns None on irrecoverable failure (caller must HARNESS_BREAK).
    """
    if not text:
        return None
    s = unicodedata.normalize("NFC", text)
    s = _BOM.sub("", s)
    s = _CR.sub("\n", s)

    # Strip fences first; a fenced ```json ... ``` is the common case.
    m = _FENCE_BLOCK.search(s)
    if m:
        s = m.group(1)

    candidate = _extract_balanced_json(s)
    if candidate is None:
        return None

    # Repair common quantized-model JSON mistakes: trailing commas, single quotes.
    repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        # Second pass: swap stray single-quoted keys/strings.
        try:
            return json.loads(re.sub(r"'", '"', repaired))
        except json.JSONDecodeError:
            return None


__all__ = ["scrub_structural", "scrub_json"]
