"""scripts/curiosity.py — CLI for Seven's curiosity inbox.

Usage:
    python -m scripts.curiosity                 # list open questions
    python -m scripts.curiosity list             # alias
    python -m scripts.curiosity stats
    python -m scripts.curiosity answer <id> "your answer text"
    python -m scripts.curiosity dismiss <id> [reason]
    python -m scripts.curiosity ask <asked_by> "question text"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import curiosity  # type: ignore


def _show(q: dict) -> None:
    sal = q.get('salience') or 0
    bar = '!!!' if sal >= 0.95 else '!! ' if sal >= 0.85 else '!  ' if sal >= 0.7 else '   '
    print(f"#{q['id']:>4}  {bar} sal={sal:.2f}  by={q['asked_by']:<14} {q.get('context_kind') or '-'}")
    print(f"        Q: {q['question']}")
    if q.get('options'):
        for o in q['options']:
            print(f"           • {o}")
    print()


def cmd_list() -> int:
    rows = curiosity.list_open(limit=50)
    if not rows:
        print("(no open questions · Seven knows what he needs to know)")
        return 0
    print(f"{len(rows)} open question(s):\n")
    for q in rows:
        _show(q)
    return 0


def cmd_stats() -> int:
    s = curiosity.stats()
    for k in ('open', 'answered', 'dismissed', 'expired'):
        print(f"  {k:>10}: {s.get(k, 0)}")
    age = s.get('latest_open_age_h')
    if age is not None:
        print(f"  latest_open_age_h: {age:.2f}")
    return 0


def cmd_answer(qid: str, *parts: str) -> int:
    text = ' '.join(parts).strip()
    if not text:
        print("error: answer text required", file=sys.stderr)
        return 2
    ok = curiosity.answer(int(qid), text, answered_by='user')
    print('ok' if ok else 'failed (already answered, or unknown id)')
    return 0 if ok else 1


def cmd_dismiss(qid: str, *parts: str) -> int:
    reason = ' '.join(parts).strip() or None
    ok = curiosity.dismiss(int(qid), reason=reason)
    print('ok' if ok else 'failed')
    return 0 if ok else 1


def cmd_ask(asked_by: str, *parts: str) -> int:
    q = ' '.join(parts).strip()
    if not asked_by or not q:
        print("error: asked_by and question required", file=sys.stderr)
        return 2
    qid = curiosity.ask(asked_by, q, salience=0.7)
    print(f"queued #{qid}" if qid else "rejected")
    return 0 if qid else 1


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ('list', 'open', '-l'):
        return cmd_list()
    cmd = argv[0]
    rest = argv[1:]
    if cmd == 'stats':
        return cmd_stats()
    if cmd == 'answer':
        if len(rest) < 2:
            print("usage: answer <id> <text>", file=sys.stderr); return 2
        return cmd_answer(rest[0], *rest[1:])
    if cmd == 'dismiss':
        if not rest:
            print("usage: dismiss <id> [reason]", file=sys.stderr); return 2
        return cmd_dismiss(rest[0], *rest[1:])
    if cmd == 'ask':
        if len(rest) < 2:
            print("usage: ask <asked_by> <question>", file=sys.stderr); return 2
        return cmd_ask(rest[0], *rest[1:])
    print(__doc__); return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
