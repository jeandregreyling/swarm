"""
load_project_docs.py — Seven's Swarm
Populate the project_docs table from PROJECT.md (split into sections).
Run this any time PROJECT.md is updated to refresh agent context.

Usage:
    python3 load_project_docs.py
"""

import os
import sys
import re
from pathlib import Path

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)
from database import get_connection

PROJECT_MD = Path(__file__).parent / 'PROJECT.md'


def parse_sections(text: str) -> list[tuple[str, str]]:
    """
    Split markdown into sections by ## headings.
    Returns list of (section_name, content) tuples.
    The content before the first ## becomes 'overview'.
    """
    # Split on lines that start with ## (but not ###)
    pattern = re.compile(r'^(#{1,2} .+)$', re.MULTILINE)
    parts = pattern.split(text)

    sections = []
    if parts[0].strip():
        sections.append(('overview', parts[0].strip()))

    i = 1
    while i < len(parts) - 1:
        heading = parts[i].lstrip('#').strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ''
        if body:
            sections.append((heading, body))
        i += 2

    return sections


def load():
    if not PROJECT_MD.exists():
        print(f'ERROR: {PROJECT_MD} not found')
        sys.exit(1)

    text = PROJECT_MD.read_text(encoding='utf-8')
    sections = parse_sections(text)

    conn = get_connection()

    # Clear old project_docs entirely
    conn.execute('DELETE FROM project_docs')
    conn.commit()

    inserted = 0
    for name, content in sections:
        # Truncate very long sections to ~4000 chars to stay token-efficient
        if len(content) > 4000:
            content = content[:4000] + '\n… [truncated]'
        conn.execute(
            'INSERT INTO project_docs (doc_name, content) VALUES (?, ?)',
            (name, content)
        )
        inserted += 1

    conn.commit()
    conn.close()

    print(f'Loaded {inserted} sections from PROJECT.md into project_docs:')
    for name, content in sections:
        print(f'  [{len(content):5d} chars] {name}')


if __name__ == '__main__':
    load()
