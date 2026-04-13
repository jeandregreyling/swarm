"""
proposal_review.py — Duck's proposal sanity-check + chat-thread notification.

Pipeline:
  alm_create_proposal → duck_review_proposal()  → approved → agent gets start signal
  agent builds        → alm_complete → status=done → duck_check_done() → uat
  ghost reviews UAT   → mark executed (or tells duck to)
"""

import sys
import time

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')


# ── Duck sanity check (rule-based, fast) ──────────────────────────────────────

def _duck_verdict(title: str, description: str, agent: str) -> tuple[str, str]:
    """Returns (verdict, note) where verdict is 'approved' or 'rejected'."""
    title_low = (title or '').lower()
    desc_low  = (description or '').lower()
    combined  = f'{title_low} {desc_low}'

    red_flags = [
        'delete all', 'drop table', 'rm -rf', 'format disk',
        'wipe ', 'destroy ', 'shutdown prod', 'kill server',
    ]
    for flag in red_flags:
        if flag in combined:
            return 'rejected', f'Duck flagged destructive language: "{flag}"'

    if len((description or '').strip()) < 20:
        return 'rejected', 'Description too short — needs more detail before work can start.'

    if len((title or '').strip()) < 5:
        return 'rejected', 'Title too short — please provide a clear proposal title.'

    note = (
        f'Duck reviewed this proposal from {agent}. '
        'Title and description look reasonable. No red flags detected. '
        'Approved — agent can start building in DEV.'
    )
    return 'approved', note


# ── Phase 1: Duck reviews new proposal ───────────────────────────────────────

def duck_review_proposal(proposal_id: str, title: str, description: str,
                         agent: str, source_conv_id=None):
    """
    Called after alm_create_proposal.
    1. Sanity check
    2. Set status: pending → approved / rejected
    3. Post result back to chat thread with start instructions
    """
    time.sleep(1)  # let the INSERT commit fully

    verdict, note = _duck_verdict(title, description, agent)

    try:
        from database import get_connection
        conn = get_connection()
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

    if source_conv_id:
        _notify_review(
            conv_id=int(source_conv_id),
            proposal_id=proposal_id,
            verdict=verdict,
            note=note,
            agent=agent,
        )

    print(f'[Duck] {proposal_id} review → {verdict}')


def _notify_review(conv_id: int, proposal_id: str, verdict: str,
                   note: str, agent: str):
    """Post Duck review result back to the originating chat thread."""
    icon  = '✅' if verdict == 'approved' else '❌'
    label = 'APPROVED' if verdict == 'approved' else 'REJECTED'

    if verdict == 'approved':
        msg = (
            f'{icon} **Duck Review — {proposal_id} {label}**\n\n'
            f'{note}\n\n'
            f'**{agent.capitalize()}, start building now:**\n'
            f'```\nSKILL alm_self_approve {proposal_id}\n```\n'
            'Make your changes with `SKILL fs_write` / `SKILL fs_patch`, '
            f'then run `SKILL alm_complete {proposal_id}` when done. '
            'Duck will check the work before it goes to UAT.'
        )
    else:
        msg = (
            f'{icon} **Duck Review — {proposal_id} {label}**\n\n'
            f'{note}\n\n'
            '_Revise the proposal description and re-submit._'
        )

    _post_to_thread(conv_id, msg, 'proposal_review')


# ── Phase 2: Duck checks completed work ──────────────────────────────────────

def duck_check_done(proposal_id: str):
    """
    Called automatically when an agent marks a proposal as done.
    Checks the work, then:
      - passes  → sets status to 'uat', notifies chat
      - fails   → sets status back to 'in_progress', notifies chat with feedback
    """
    time.sleep(1)

    try:
        from database import get_connection
        conn = get_connection()
        row = conn.execute(
            'SELECT proposal_id, title, description, agent, source_conv_id, status '
            'FROM work_proposals WHERE proposal_id=?',
            (proposal_id,)
        ).fetchone()
        conn.close()
    except Exception as exc:
        print(f'[Duck] check_done DB read failed: {exc}')
        return

    if not row:
        print(f'[Duck] check_done: proposal {proposal_id} not found')
        return

    if str(row['status'] or '') != 'done':
        return  # already moved on

    title       = row['title'] or proposal_id
    description = row['description'] or ''
    agent       = row['agent'] or 'agent'
    conv_id     = row['source_conv_id']

    # Quality check — rule-based fast pass
    verdict, feedback = _duck_quality_check(title, description)

    try:
        from database import get_connection
        conn = get_connection()
        new_status = 'uat' if verdict == 'pass' else 'in_progress'
        duck_note = feedback
        conn.execute(
            """UPDATE work_proposals
               SET status=?, duck_note=?, updated_at=CURRENT_TIMESTAMP
               WHERE proposal_id=?""",
            (new_status, duck_note, proposal_id)
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f'[Duck] check_done DB update failed: {exc}')
        return

    if conv_id:
        _notify_done_check(int(conv_id), proposal_id, title, agent, verdict, feedback)

    print(f'[Duck] {proposal_id} quality check → {verdict} → {new_status}')


def _duck_quality_check(title: str, description: str) -> tuple[str, str]:
    """
    Basic quality gate before UAT.
    Returns (verdict, feedback) where verdict is 'pass' or 'fail'.
    """
    combined = f'{(title or "").lower()} {(description or "").lower()}'

    # Fail: incomplete work signals
    incomplete_signals = ['todo', 'tbd', 'placeholder', 'not yet', 'incomplete', 'wip']
    for sig in incomplete_signals:
        if sig in combined:
            return 'fail', f'Duck found incomplete-work signal: "{sig}". Revise and re-complete.'

    return 'pass', (
        'Duck quality check passed. Work looks complete and reasonable. '
        'Proposal is now in UAT — Ghost can review and mark as executed to go live, '
        'or ask Duck to do it.'
    )


def _notify_done_check(conv_id: int, proposal_id: str, title: str,
                        agent: str, verdict: str, feedback: str):
    """Notify chat thread of Duck's quality verdict after work is done."""
    if verdict == 'pass':
        msg = (
            f'🦆 **Duck QA Check — {proposal_id} PASSED**\n\n'
            f'{feedback}\n\n'
            f'**Ghost:** review in Studio → UAT tab, then mark as Executed to ship to production. '
            f'Or tell Duck: _"Duck, execute {proposal_id}"_ to do it automatically.'
        )
    else:
        msg = (
            f'🦆 **Duck QA Check — {proposal_id} NEEDS WORK**\n\n'
            f'{feedback}\n\n'
            f'**{agent.capitalize()}:** proposal is back to In Progress. '
            f'Fix the issue and run `SKILL alm_complete {proposal_id}` again.'
        )

    _post_to_thread(conv_id, msg, 'proposal_review')


# ── Phase 3: Duck executes UAT → production on Ghost's command ───────────────

def duck_execute_proposal(proposal_id: str, actor: str = 'duck'):
    """
    Called when Ghost tells Duck to execute (ship) a UAT proposal.
    Sets status to executed and notifies the thread.
    """
    try:
        from database import get_connection
        conn = get_connection()
        row = conn.execute(
            'SELECT proposal_id, title, agent, source_conv_id, status '
            'FROM work_proposals WHERE proposal_id=?',
            (proposal_id,)
        ).fetchone()
        conn.close()
    except Exception as exc:
        return False, f'DB read failed: {exc}'

    if not row:
        return False, f'Proposal {proposal_id} not found'

    status = str(row['status'] or '')
    if status not in ('uat', 'done', 'approved'):
        return False, f'Proposal is {status} — needs to be in UAT before executing'

    try:
        from database import get_connection
        conn = get_connection()
        conn.execute(
            "UPDATE work_proposals SET status='executed', updated_at=CURRENT_TIMESTAMP WHERE proposal_id=?",
            (proposal_id,)
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        return False, f'DB update failed: {exc}'

    conv_id = row['source_conv_id']
    if conv_id:
        msg = (
            f'🚀 **{proposal_id} — EXECUTED by {actor}**\n\n'
            f'"{row["title"]}" is now live in production. '
            'Proposal closed. 🦆'
        )
        _post_to_thread(int(conv_id), msg, 'proposal_update')

    print(f'[Duck] {proposal_id} executed by {actor}')
    return True, f'Proposal {proposal_id} executed and closed.'


# ── Status-change notification (manual moves via Studio UI) ──────────────────

def notify_proposal_status_change(proposal_id: str, new_status: str,
                                   actor: str = 'ghost', note: str = ''):
    """
    Called when Ghost (or agent) manually changes status via PATCH /api/work-proposals/<id>.
    Posts status update back to originating chat thread.
    Also triggers duck_check_done() when status becomes 'done'.
    """
    try:
        from database import get_connection
        conn = get_connection()
        row = conn.execute(
            'SELECT source_conv_id, title, agent FROM work_proposals WHERE proposal_id=?',
            (proposal_id,)
        ).fetchone()
        conn.close()
    except Exception as exc:
        print(f'[ProposalReview] Status notify DB read failed: {exc}')
        return

    conv_id = int(row['source_conv_id']) if row and row['source_conv_id'] else None
    title   = (row['title'] or proposal_id) if row else proposal_id
    creator = (row['agent'] or 'agent') if row else 'agent'

    status_icons = {
        'approved':    '✅',
        'rejected':    '❌',
        'in_progress': '🔧',
        'done':        '🎉',
        'uat':         '🧪',
        'executed':    '🚀',
    }
    icon = status_icons.get(new_status, '📋')

    if new_status == 'in_progress':
        msg = (
            f'🔧 **Proposal started — {title}**\n\n'
            f'{actor.capitalize()} has kicked off the build. '
            f'{creator.capitalize()}, make your changes with `SKILL fs_write` / `SKILL fs_patch`, '
            f'then run `SKILL alm_complete {proposal_id}` when done.'
        )
    elif new_status == 'approved':
        msg = (
            f'✅ **Proposal approved — {title}**\n\n'
            f'Approved by {actor}. {creator.capitalize()}, run:\n'
            f'```\nSKILL alm_self_approve {proposal_id}\n```\nto begin.'
        )
    elif new_status == 'uat':
        msg = (
            f'🧪 **Proposal in UAT — {title}**\n\n'
            f'Moved to UAT by {actor}. Ghost will review and mark as executed to go live.'
        )
    elif new_status == 'executed':
        msg = (
            f'🚀 **Proposal executed — {title}**\n\n'
            f'Shipped to production by {actor}. Proposal closed.'
        )
    elif new_status == 'rejected':
        msg = (
            f'❌ **Proposal rejected — {title}**\n\n'
            f'Rejected by {actor}.'
            + (f'\n\n_{note}_' if note else '')
        )
    else:
        msg = (
            f'{icon} **Proposal update — {title}**\n'
            f'Status → **{new_status.upper()}** by {actor}.'
            + (f'\n\n_{note}_' if note else '')
        )

    if conv_id:
        _post_to_thread(conv_id, msg, 'proposal_update')

    # When manually moved to done, trigger Duck quality check
    if new_status == 'done':
        import threading as _t
        _t.Thread(target=duck_check_done, args=(proposal_id,), daemon=True).start()


# ── Shared helper ─────────────────────────────────────────────────────────────

def _post_to_thread(conv_id: int, msg: str, message_type: str = 'proposal_update'):
    """Log a Duck message to a conversation, silently ignoring errors."""
    try:
        from database import get_connection, log_message
        conn = get_connection()
        exists = conn.execute('SELECT 1 FROM conversations WHERE id=?', (conv_id,)).fetchone()
        conn.close()
        if not exists:
            return
        log_message(conv_id, 'duck', msg, to_agent='user', message_type=message_type)
    except Exception as exc:
        print(f'[ProposalReview] _post_to_thread failed: {exc}')
