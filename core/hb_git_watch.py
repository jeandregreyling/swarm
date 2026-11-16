"""Commits made outside HB's change sets show in main chat and on their Studio step (Practice 109, owner 16 Nov 2026).

JD: "are all these git changes also shown in main chat and its studio sections?" They were not. HB announces the commits it makes itself
(a change set an agent applied: "✅ Done ..."), but commits made by hand - Claude Code committing work that was running but never saved,
or committing what APEX wrote itself - appeared nowhere in HB. Now HB's loop looks at the repository's HEAD: every new commit that is
not one of HB's own change-set commits gets one plain line in the chat JD uses (what, who, which files), and when its message names a
Studio step (S-XXXXXXXXXX) the commit is recorded on that step's task as well.
"""
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEP_RE = re.compile(r'\bS-[0-9A-F]{10}\b')
MAX_COMMITS = 20
EVERY_S = 60
_LAST = [0.0]


def _git(root, *args):
    out = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=30)
    return out.stdout if out.returncode == 0 else ''


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_git_seen(name TEXT PRIMARY KEY, commit_hash TEXT, at REAL)')


def commits_since(root, old, new):
    """[(hash, short, author, subject, body, files)] from old (exclusive) to new, oldest first."""
    raw = _git(root, 'log', f'--max-count={MAX_COMMITS}', '--reverse', '--format=%H%x1f%h%x1f%an%x1f%s%x1f%b%x1e', f'{old}..{new}')
    out = []
    for rec in raw.split('\x1e'):
        parts = rec.strip('\n').split('\x1f')
        if len(parts) < 5:
            continue
        files = [f for f in _git(root, 'show', '--name-only', '--format=', parts[0]).splitlines() if f.strip()]
        out.append((parts[0], parts[1], parts[2], parts[3], parts[4], files))
    return out


def tick(conn, root=None, now=None, every=EVERY_S):
    """Announce new commits made outside HB's change sets. Returns how many were announced."""
    root = root or ROOT
    now = time.time() if now is None else now
    if now - _LAST[0] < every:
        return 0
    _LAST[0] = now
    ensure_schema(conn)
    head = _git(root, 'rev-parse', 'HEAD').strip()
    if not head:
        return 0
    row = conn.execute("SELECT commit_hash FROM hb_git_seen WHERE name='head'").fetchone()
    conn.execute("INSERT INTO hb_git_seen(name, commit_hash, at) VALUES ('head', ?, ?) ON CONFLICT(name) DO UPDATE SET "
                 "commit_hash=excluded.commit_hash, at=excluded.at", (head, now))
    if not row or row[0] == head:
        return 0                                     # first look: remember where HEAD is, announce nothing old
    from core.hb_chat import owner_chat
    from core.hb_plain import message
    from core import hb_tasks
    told = 0
    for full, short, author, subject, body, files in commits_since(root, row[0], head):
        if subject.startswith('HB change set '):
            continue                                 # HB already said "Done" for its own change sets
        steps = list(dict.fromkeys(STEP_RE.findall(subject + '\n' + body)))
        shown = ', '.join(files[:8]) + (f' and {len(files) - 8} more' if len(files) > 8 else '')
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (owner_chat(conn), message(f'📦 Committed outside HB\'s change sets: {subject[:160]}',
                                                f'{len(files)} file(s), by {author}, commit {short}.',
                                                details=[f'files: {shown}' if files else 'no files',
                                                         *(f'Studio step {s}' for s in steps)])))
        for step_id in steps:
            task = conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? ORDER BY created_at DESC LIMIT 1", (step_id,)).fetchone() \
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_tasks'").fetchone() else None
            if task:
                hb_tasks.event(conn, hb_tasks.get(conn, task[0]), 'hummingbird', 'commit_recorded',
                               {'commit': full, 'short': short, 'subject': subject[:200], 'files': files[:40], 'author': author})
        told += 1
    return told
