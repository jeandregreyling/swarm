"""
git_commit_logger.py — Seven's Swarm Time Wizard git hook
═══════════════════════════════════════════════════════════════════════════════
Called by .git/hooks/post-commit after every git commit.

For each commit this script:
  1. Parses the commit message for [agent] prefix
  2. Creates a decisions entry (test_status='PASS')
  3. For every changed .py or .md file: creates a time_machine entry
     with before (HEAD~1) and after (HEAD) content
  4. Marks any open work_proposals for that agent as 'executed'

This ensures ALL changes — whether made by Nine, Ghost, or any agent —
are automatically logged to the Time Wizard without any manual effort.
═══════════════════════════════════════════════════════════════════════════════
"""

import subprocess
import sys
import hashlib
import os

SWARM_ROOT = '/home/seven/swarm'
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'utils'))

# File extensions to capture full before/after content
TEXT_EXTENSIONS = {'.py', '.md', '.txt', '.json', '.yaml', '.yml', '.html', '.js', '.css', '.sh'}
# Max content size to store per file (60KB)
MAX_CONTENT = 60_000


def _run(cmd, cwd=SWARM_ROOT):
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.stdout.strip()


def get_commit_hash():
    return _run(['git', 'rev-parse', '--short', 'HEAD'])


def get_commit_message():
    return _run(['git', 'log', '-1', '--pretty=%s'])


def get_changed_files():
    """List of files changed in HEAD commit."""
    out = _run(['git', 'diff-tree', '--no-commit-id', '-r', '--name-only', 'HEAD'])
    return [f for f in out.splitlines() if f.strip()]


def get_file_at_ref(file_path, ref):
    """Get file content at git ref. Returns '' if missing."""
    result = subprocess.run(
        ['git', 'show', f'{ref}:{file_path}'],
        capture_output=True, text=True, cwd=SWARM_ROOT
    )
    return result.stdout if result.returncode == 0 else ''


def parse_agent(commit_msg):
    """Extract agent from '[agent] message' format. Falls back to 'unknown'."""
    msg = commit_msg.strip()
    if msg.startswith('[') and ']' in msg:
        return msg[1:msg.index(']')].lower()
    return 'unknown'


def _hash(content):
    if not content:
        return ''
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def is_first_commit():
    """True if HEAD has no parent (initial commit)."""
    result = subprocess.run(
        ['git', 'rev-parse', '--verify', 'HEAD~1'],
        capture_output=True, text=True, cwd=SWARM_ROOT
    )
    return result.returncode != 0


def main():
    from database import get_connection

    commit_hash = get_commit_hash()
    commit_msg = get_commit_message()
    agent = parse_agent(commit_msg)
    changed_files = get_changed_files()
    first_commit = is_first_commit()

    print(f'[TimeWizard] Logging commit {commit_hash} by [{agent}]: {len(changed_files)} files')

    conn = get_connection()
    try:
        # Create decisions entry for this commit
        cursor = conn.execute(
            """INSERT INTO decisions
               (agent, component, decision, reasoning, test_status, commit_hash, proposal_file)
               VALUES (?, ?, ?, ?, 'PASS', ?, '')""",
            (agent, 'git-commit', commit_msg[:200],
             f'Auto-logged by git post-commit hook from {commit_hash}',
             commit_hash)
        )
        decision_id = cursor.lastrowid
        conn.commit()

        logged = 0
        for file_path in changed_files:
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in TEXT_EXTENSIONS:
                continue

            after = get_file_at_ref(file_path, 'HEAD')
            before = '' if first_commit else get_file_at_ref(file_path, 'HEAD~1')

            if before == after:
                continue

            conn.execute(
                """INSERT INTO time_machine
                   (agent, file_path, before_code, after_code, before_hash, after_hash,
                    decision_id, commit_hash, outcome, is_rollback_point)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'success', 0)""",
                (agent, file_path,
                 before[:MAX_CONTENT], after[:MAX_CONTENT],
                 _hash(before), _hash(after),
                 decision_id, commit_hash)
            )
            logged += 1

        conn.commit()

        # Mark any open work_proposals for this agent as executed
        conn.execute(
            """UPDATE work_proposals
               SET status='executed', updated_at=datetime('now')
               WHERE status='pending' AND agent=?""",
            (agent,)
        )
        conn.commit()

    finally:
        conn.close()

    print(f'[TimeWizard] decision_id={decision_id} | {logged} file snapshots stored')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # Never fail the commit — just warn
        print(f'[TimeWizard] Hook error (commit still succeeded): {e}', file=sys.stderr)
        sys.exit(0)
