"""ops.reconcile_stale_proposals — idempotently dedupe STALE_PROPOSALS.md.

Migrated story: MD-STALE-PROPOSALS-RECONCILE-20260430.

Background:
    fridays/orchestrator.py::_check_stale_proposals() appended a line to
    sandpits/shared/STALE_PROPOSALS.md on every heartbeat for every stale
    proposal, with no de-dup. The file accumulated ~6800 lines (mostly the
    same handful of IDs over and over).

This module:
  * Reads the file (best-effort).
  * Groups entries by ``proposal_id``.
  * Optionally cross-references current Studio proposals (so we don't keep
    surfacing IDs that no longer exist in the system).
  * Rewrites the file with one entry per surviving id, preserving the
    earliest seen heartbeat timestamp.

CLI:
    python -m ops.reconcile_stale_proposals          # in-place reconcile
    python -m ops.reconcile_stale_proposals --dry-run

Importable: ``reconcile_file(path, *, dry_run=False, known_ids=None)``.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Lines look like:
#   - [13:13] STUDIO-PROPOSALS-0001 (studio): Improve ALM/Studio Proposals UI
_LINE_RE = re.compile(
    r'^\s*-\s*\[(?P<ts>[^\]]+)\]\s+(?P<pid>[A-Z0-9][A-Z0-9_\-]+)\s*'
    r'(?:\((?P<agent>[^)]*)\))?\s*:?\s*(?P<title>.*?)\s*$'
)

DEFAULT_PATH = Path(__file__).resolve().parent.parent / 'sandpits' / 'shared' / 'STALE_PROPOSALS.md'


def parse_lines(text: str) -> List[Dict[str, str]]:
    """Parse a STALE_PROPOSALS.md body into a list of entry dicts.

    Header lines (starting with '#') and blank lines are skipped. Lines that
    don't match the expected shape are also skipped.
    """
    entries: List[Dict[str, str]] = []
    for raw in (text or '').splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith('#'):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        entries.append({
            'ts': m.group('ts').strip(),
            'proposal_id': m.group('pid').strip(),
            'agent': (m.group('agent') or '').strip(),
            'title': (m.group('title') or '').strip(),
        })
    return entries


def dedupe(entries: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    """Collapse to one entry per proposal_id, keeping the first-seen timestamp
    and the longest title (titles can be truncated in some heartbeats).
    Stable order: order of first appearance."""
    seen: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for e in entries:
        pid = e.get('proposal_id') or ''
        if not pid:
            continue
        if pid not in seen:
            seen[pid] = dict(e)
            order.append(pid)
        else:
            existing = seen[pid]
            # Prefer the longest title we've seen.
            if len(e.get('title') or '') > len(existing.get('title') or ''):
                existing['title'] = e['title']
            # Keep agent if previously empty.
            if not existing.get('agent') and e.get('agent'):
                existing['agent'] = e['agent']
    return [seen[k] for k in order]


def render(entries: Iterable[Dict[str, str]]) -> str:
    """Render the canonical STALE_PROPOSALS.md body."""
    out = ['# Stale Proposals', '']
    for e in entries:
        agent = f" ({e['agent']})" if e.get('agent') else ''
        title = f": {e['title']}" if e.get('title') else ''
        out.append(f"- [{e.get('ts', '')}] {e['proposal_id']}{agent}{title}".rstrip())
    out.append('')  # trailing newline
    return '\n'.join(out)


def reconcile_file(
    path: Path | str = DEFAULT_PATH,
    *,
    dry_run: bool = False,
    known_ids: Optional[Iterable[str]] = None,
) -> Dict[str, object]:
    """Reconcile a STALE_PROPOSALS.md file in place (or report the diff).

    Returns a summary dict with counts and the would-be content.
    """
    p = Path(path)
    text = p.read_text() if p.exists() else ''
    entries = parse_lines(text)
    deduped = dedupe(entries)
    filtered = deduped
    dropped_unknown: List[str] = []
    if known_ids is not None:
        known_set = {str(x) for x in known_ids}
        filtered = []
        for e in deduped:
            if e['proposal_id'] in known_set:
                filtered.append(e)
            else:
                dropped_unknown.append(e['proposal_id'])
    new_text = render(filtered)
    summary = {
        'path': str(p),
        'before_lines': len(text.splitlines()),
        'parsed_entries': len(entries),
        'unique_ids': len(deduped),
        'kept': len(filtered),
        'dropped_unknown': dropped_unknown,
        'after_lines': len(new_text.splitlines()),
        'changed': new_text != text,
        'new_text': new_text,
    }
    if not dry_run and summary['changed']:
        p.write_text(new_text)
    return summary


def _load_known_proposal_ids() -> List[str]:
    """Best-effort lookup of currently-known proposal ids from the DB."""
    try:
        import sqlite3
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT proposal_id FROM proposals"
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows if r and r[0]]
    except Exception:
        return []


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description='Reconcile STALE_PROPOSALS.md')
    p.add_argument('--path', default=str(DEFAULT_PATH))
    p.add_argument('--dry-run', action='store_true',
                   help='Print summary without rewriting the file.')
    p.add_argument('--cross-ref-db', action='store_true',
                   help='Drop entries whose proposal_id is not in the DB.')
    args = p.parse_args(argv)

    known_ids: Optional[List[str]] = None
    if args.cross_ref_db:
        known_ids = _load_known_proposal_ids()

    summary = reconcile_file(args.path, dry_run=args.dry_run, known_ids=known_ids)
    print(f"path           {summary['path']}")
    print(f"before_lines   {summary['before_lines']}")
    print(f"parsed_entries {summary['parsed_entries']}")
    print(f"unique_ids     {summary['unique_ids']}")
    print(f"kept           {summary['kept']}")
    if summary['dropped_unknown']:
        print(f"dropped_unknown ({len(summary['dropped_unknown'])}): "
              f"{', '.join(summary['dropped_unknown'][:20])}"
              + (' ...' if len(summary['dropped_unknown']) > 20 else ''))
    print(f"after_lines    {summary['after_lines']}")
    print(f"changed        {summary['changed']}")
    if args.dry_run:
        print('--- new content (dry run, not written) ---')
        print(summary['new_text'][:2000])
    return 0


if __name__ == '__main__':
    sys.exit(main())
