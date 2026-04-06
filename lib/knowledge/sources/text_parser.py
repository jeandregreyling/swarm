"""lib/knowledge/sources/text_parser.py — Normalise pasted plain text."""
import re


def extract(raw_text, max_chars=200_000):
    """
    Normalise raw pasted text for ingestion.
    Collapses excessive blank lines, strips leading/trailing whitespace.
    Returns cleaned string (truncated to max_chars).
    """
    text = (raw_text or '').strip()
    # Collapse 4+ blank lines → 2
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text[:max_chars]
