"""Seven's self-awareness layer.

Pulls together everything Seven needs to talk about himself, the build, and
the standard, on every turn:

- The Standard (`docs/the-standard.md`) — Seven's contract.
- The latest bullshit-detector report — Seven's quality signal.
- Recent learned lessons — Seven's bias.
- Recent commits — Seven's short-term memory of what shipped.

All loaders are defensive: if any source is missing, the others still work.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STANDARD_PATH = ROOT / 'docs' / 'the-standard.md'


def load_standard_excerpt(max_chars: int = 1400) -> str:
    """Return a tight excerpt of the standard for the LLM system prompt.
    We keep section 1 (Identity), 2 (Forbidden List), 6 (Seven Standard) and
    truncate hard so we don't blow the context budget.
    """
    if not STANDARD_PATH.exists():
        return "(the-standard.md missing)"
    try:
        text = STANDARD_PATH.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return "(the-standard.md unreadable)"
    # Pull "## 1." through end of "## 2." plus "## 6."
    parts = text.split('\n## ')
    keep = []
    for p in parts:
        head = p.split('\n', 1)[0]
        if head.startswith(('1.', '2.', '6.')):
            keep.append('## ' + p)
    excerpt = ('\n'.join(keep)).strip() or text
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rsplit('\n', 1)[0] + '\n…'
    return excerpt


def load_bullshit_summary() -> dict:
    try:
        from ops.bullshit_detector import summary_for_seven
        return summary_for_seven()
    except Exception as exc:
        return {'pillar': 'bullshit-detector', 'ok': False, 'error': str(exc)}


def load_recent_commits(n: int = 5) -> list[dict]:
    try:
        out = subprocess.run(
            ['git', '-C', str(ROOT), 'log', f'-{n}', '--pretty=%h%x09%s%x09%cr'],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode != 0:
            return []
        rows = []
        for line in out.stdout.strip().splitlines():
            parts = line.split('\t')
            if len(parts) >= 3:
                rows.append({'sha': parts[0], 'subject': parts[1], 'when': parts[2]})
        return rows
    except Exception:
        return []


def load_recent_lessons() -> str:
    try:
        from agents.seven import learnings
        return learnings.recent_lessons_block(limit=4)
    except Exception:
        return "(learnings module unavailable)"


def context_block(max_chars: int = 2400) -> str:
    """Compact LLM-friendly self-awareness block.

    Layout:
      THE STANDARD (excerpt)
      BUILD QUALITY (bullshit detector stamp+score)
      LESSONS LEARNED (recent positive/negative)
      RECENT COMMITS
    """
    standard = load_standard_excerpt(max_chars=900)
    bs = load_bullshit_summary()
    if bs.get('ok'):
        bs_line = (
            f"Stamp={bs.get('stamp', '?')}  Score={bs.get('score', 0)}/100  "
            f"critical={bs.get('critical', 0)}  warnings={bs.get('warnings', 0)}  "
            f"info={bs.get('info', 0)}  pillar_issues={bs.get('pillar_findings', 0)}"
        )
    else:
        bs_line = f"(bullshit detector offline: {bs.get('error', '?')})"

    lessons = load_recent_lessons()
    commits = load_recent_commits(n=4)
    if commits:
        commit_lines = '\n'.join(f"  · {c['sha']} {c['subject']} ({c['when']})" for c in commits)
    else:
        commit_lines = "  (git log unavailable)"

    out = (
        "THE STANDARD (excerpt — Seven holds the user AND himself to this):\n"
        f"{standard}\n\n"
        f"BUILD QUALITY (live from bullshit detector): {bs_line}\n\n"
        f"LESSONS LEARNED:\n{lessons}\n\n"
        f"RECENT COMMITS:\n{commit_lines}"
    )
    if len(out) > max_chars:
        out = out[:max_chars].rsplit('\n', 1)[0] + '\n…'
    return out


def audit_report() -> str:
    """Human-readable audit Seven prints when asked '/audit' or 'is this up to standard'."""
    bs = load_bullshit_summary()
    lines = [f"Seven audit — {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    if bs.get('ok'):
        stamp = bs.get('stamp', '?')
        emoji = {'GREEN': '🟢', 'AMBER': '🟡', 'RED': '🔴'}.get(stamp, '⚪')
        lines += [
            f"  {emoji} Stamp: {stamp}",
            f"  Score: {bs.get('score', 0)}/100",
            f"  Critical: {bs.get('critical', 0)}",
            f"  Warnings: {bs.get('warnings', 0)}",
            f"  Info:     {bs.get('info', 0)}",
            f"  Pillar contract issues: {bs.get('pillar_findings', 0)}",
        ]
        top = bs.get('top_hits') or []
        if top:
            lines.append("  Top hits:")
            for h in top:
                lines.append(f"    · [{h['severity']}] {h['path']}:{h['line']} {h['rule']}")
    else:
        lines.append(f"  Detector offline: {bs.get('error', '?')}")
    lessons = load_recent_lessons()
    lines += ["", "Lessons in play:", lessons]
    commits = load_recent_commits(n=3)
    if commits:
        lines.append("\nRecent ship history:")
        for c in commits:
            lines.append(f"  · {c['sha']} {c['subject']} ({c['when']})")
    return '\n'.join(lines)
