"""
proposal_review.py — Duck's proposal sanity-check + chat-thread notification.

Called from fridays/skills.py after alm_create_proposal creates a new proposal.
Duck reviews the proposal, approves or rejects it, updates the DB, and posts
a notification back to the originating chat thread so Ghost sees the verdict
in the same place the proposal was raised.
"""

import sys
import time

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')


def _duck_verdict(title: str, description: str, agent: str) -> tuple[str, str]:
    """
    Fast rule-based Duck sanity check for proposals.
    Returns (verdict, note) where verdict is 'approved' or 'rejected'.
    """
    title_low = (title or '').lower()
    desc_low  = (description or '').lower()
    combined  = f'{title_low} {desc_low}'

    # Reject: destructive / out-of-scope actions
    red_flags = [
        'delete all', 'drop table', 'rm -rf', 'format disk',
        'wipe ', 'destroy ', 'shutdown prod', 'kill server',
    ]
    for flag in red_flags:
        if flag in combined:
            return 'rejected', f'Duck flagged destructive language: "{flag}"'

    # Reject: too vague to act on
    if len((description or '').strip()) < 20:
        return 'rejected', 'Description too short — needs more detail before Ghost can act on it.'

    # Reject: no title
    if len((title or '').strip()) < 5:
        return 'rejected', 'Title too short — please provide a clear proposal title.'

    # Approve otherwise
    note = (
        f'Duck reviewed this proposal from {agent}. '
        'Title and description look reasonable. No red flags detected. Approved for Ghost review.'
    )
    return 'approved', note


def duck_review_proposal(proposal_id: str, title: str, description: str,
                         agent: str, source_conv_id=None):
    """
    Full Duck review flow:
    1. Run sanity check
    2. Update proposal status + store verdict
    3. Post verdict back to originating chat thread
    """
    # Small delay so the proposal row is fully committed before we update it
    time.sleep(1)

    verdict, note = _duck_verdict(title, description, agent)

    try:
        from database import get_connection
        conn = get_connection()
        # Advance status: pending → approved / rejected
        new_status = 'approved' if verdict == 'approved' else 'rejected'
        conn.execute(
            """UPDATE work_proposals
               SET status=?, duck_verdict=?, duck_note=?, updated_at=CURRENT_TIMESTAMP
               WHERE proposal_id=?""",
            (new_status, verdict, note, proposal_id)
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f'[ProposalReview] DB update failed: {exc}')
        return

    # Post back to the originating chat thread
    if source_conv_id:
        _notify_chat_thread(
            conv_id=int(source_conv_id),
            proposal_id=proposal_id,
            verdict=verdict,
            note=note,
            agent=agent,
        )

    print(f'[Duck] Proposal {proposal_id} → {verdict}: {note[:80]}')


def _notify_chat_thread(conv_id: int, proposal_id: str, verdict: str,
                        note: str, agent: str):
    """Log a Duck message back to the originating chat conversation."""
    icon  = '✅' if verdict == 'approved' else '❌'
    label = 'APPROVED' if verdict == 'approved' else 'REJECTED'
    msg = (
        f'{icon} **Duck Review — Proposal {proposal_id} {label}**\n\n'
        f'{note}\n\n'
        f'_Raised by {agent}. You can start work or adjust the description and re-submit._'
    )
    try:
        from database import get_connection, log_message
        # Verify the conversation still exists
        conn = get_connection()
        exists = conn.execute('SELECT 1 FROM conversations WHERE id=?', (conv_id,)).fetchone()
        conn.close()
        if not exists:
            return
        log_message(conv_id, 'duck', msg, to_agent='user', message_type='proposal_review')
    except Exception as exc:
        print(f'[ProposalReview] Chat notify failed: {exc}')


def notify_proposal_status_change(proposal_id: str, new_status: str,
                                   actor: str = 'ghost', note: str = ''):
    """
    Called when Ghost or an agent manually changes proposal status via PATCH.
    Posts an update message back to the originating chat thread.
    """
    try:
        from database import get_connection, log_message
        conn = get_connection()
        row = conn.execute(
            'SELECT source_conv_id, title, agent FROM work_proposals WHERE proposal_id=?',
            (proposal_id,)
        ).fetchone()
        conn.close()
        if not row or not row['source_conv_id']:
            return
        conv_id = int(row['source_conv_id'])
        title   = row['title'] or proposal_id
        creator = row['agent'] or 'agent'

        status_icons = {
            'approved':    '✅',
            'rejected':    '❌',
            'in_progress': '🔧',
            'done':        '🎉',
            'executed':    '🚀',
        }
        icon = status_icons.get(new_status, '📋')
        msg = (
            f'{icon} **Proposal update — {title}**\n'
            f'Status changed to **{new_status.upper()}** by {actor}.'
        )
        if note:
            msg += f'\n\n_{note}_'

        conn = get_connection()
        exists = conn.execute('SELECT 1 FROM conversations WHERE id=?', (conv_id,)).fetchone()
        conn.close()
        if not exists:
            return
        log_message(conv_id, 'duck', msg, to_agent='user', message_type='proposal_update')
    except Exception as exc:
        print(f'[ProposalReview] Status notify failed: {exc}')
