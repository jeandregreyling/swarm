"""
change_logger.py — Seven's Swarm Time Wizard integration
═══════════════════════════════════════════════════════════════════════════════
Every code change made by any agent — including Nine — must flow through here.

Workflow for an agent making changes:
  1. Call propose() at the START — creates decisions (PENDING) + work_proposals
  2. Make your edits (read file → capture before → edit → capture after)
  3. Call record_file_change() for each file touched
  4. Call mark_executed() when done — sets PASS, links commit_hash

The git post-commit hook (utils/git_commit_logger.py) handles steps 3+4
automatically for every git commit. Agents can also call these functions
directly for immediate logging without waiting for a commit.

This module is the bridge between Nine's editing sessions and the Time Wizard.
═══════════════════════════════════════════════════════════════════════════════
"""

import hashlib
import logging
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')

logger = logging.getLogger('seven.change_logger')


def _hash(content):
    """Short SHA-256 hex of content string."""
    if not content:
        return ''
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def propose(agent, title, description, component='', proposal_file=''):
    """
    Register a proposal BEFORE making any changes.

    Creates:
      - decisions entry with test_status='PENDING'
      - work_proposals entry with status='pending'

    Returns decision_id (int). Pass this to record_file_change() and mark_executed().

    Example:
        decision_id = propose('nine', 'NINE-020: Fix scheduler bug',
                              'Scheduler never called check_due()',
                              component='fridays/scheduler.py',
                              proposal_file='NINE-020-fix-scheduler.md')
    """
    from database import get_connection
    from queue_manager import intake_internal
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO decisions (agent, component, proposal_file, decision, reasoning, test_status)
               VALUES (?, ?, ?, ?, ?, 'PENDING')""",
            (agent, component, proposal_file, title[:200], description[:500])
        )
        decision_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # Also create a work_proposals + queue entry
    try:
        queue_id, proposal_id = intake_internal(agent, title, description, priority=5)
        conn2 = get_connection()
        conn2.execute(
            "UPDATE work_proposals SET proposal_file=? WHERE queue_id=?",
            (proposal_file, queue_id)
        )
        conn2.commit()
        conn2.close()
    except Exception as e:
        logger.warning(f'[ChangeLogger] work_proposals entry failed: {e}')

    logger.info(f'[ChangeLogger] Proposed decision_id={decision_id} by {agent}: {title[:60]}')
    return decision_id


def record_file_change(decision_id, agent, file_path, before_content, after_content,
                       commit_hash='', test_results='', is_rollback_point=False):
    """
    Log a single file's before/after state to time_machine.

    Call once per file changed. decision_id links back to the decisions entry
    created by propose(). If no propose() was called, pass decision_id=0.

    before_content — file content BEFORE the change ('' if new file)
    after_content  — file content AFTER the change
    """
    from database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO time_machine
               (agent, file_path, before_code, after_code, before_hash, after_hash,
                test_results, decision_id, commit_hash, outcome, is_rollback_point)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'success', ?)""",
            (agent, file_path,
             before_content[:60000], after_content[:60000],
             _hash(before_content), _hash(after_content),
             test_results, decision_id, commit_hash,
             1 if is_rollback_point else 0)
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(f'[ChangeLogger] time_machine: {file_path} decision={decision_id}')


def mark_executed(decision_id, commit_hash='', test_status='PASS'):
    """
    Mark a decisions entry as executed (PASS or FAIL).
    Also marks linked work_proposals as 'executed'.

    Call after all changes are made and tested.
    """
    from database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE decisions SET test_status=?, commit_hash=? WHERE decision_id=?",
            (test_status, commit_hash, decision_id)
        )
        # Mark the work_proposal linked via proposal_file matching the decision's proposal_file
        # (The broken original query used a subquery that matched ALL pending proposals)
        conn.execute(
            """UPDATE work_proposals SET status='executed', updated_at=datetime('now')
               WHERE status='pending' AND proposal_file = (
                   SELECT proposal_file FROM decisions WHERE decision_id=?
               ) AND proposal_file != ''""",
            (decision_id,)
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(f'[ChangeLogger] decision_id={decision_id} marked {test_status} commit={commit_hash}')


def read_file_safe(path):
    """Read a file and return its content, or '' if it doesn't exist."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        return ''


def log_proposal_and_change(agent, proposal_id, title, description,
                             files_before, files_after, commit_hash='',
                             component='', test_results=''):
    """
    One-shot: log a complete proposal + all file changes in one call.

    files_before — dict of {file_path: content_before}
    files_after  — dict of {file_path: content_after}

    Returns decision_id.
    """
    decision_id = propose(agent, title, description,
                          component=component, proposal_file=proposal_id)
    for file_path in files_after:
        before = files_before.get(file_path, '')
        after = files_after[file_path]
        record_file_change(decision_id, agent, file_path, before, after,
                           commit_hash=commit_hash, test_results=test_results)
    mark_executed(decision_id, commit_hash=commit_hash)
    return decision_id
