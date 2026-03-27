"""
swarm_tasks.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Scheduled background tasks run from the listener loop.
- check_snoozed()   — wake up snoozed tickets and email Ghost
- check_sla()       — warn Ghost about tickets open too long
- send_daily_digest() — daily summary email
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')


def check_snoozed():
    """
    Check for snoozed tickets whose wake time has passed.
    Sends Ghost a reminder email + Discord ping and marks the snooze as fired.
    """
    from database import get_due_snoozed, mark_snooze_fired
    from email_handler import send_reply
    from config import GHOST_EMAIL
    import discord_notify

    due = get_due_snoozed()
    for s in due:
        ticket_number = s['ticket_number']
        note = s['note'] or '(no note)'
        body = (
            f'Snooze reminder for {ticket_number}.\r\n\r\n'
            f'Note: {note}\r\n\r\n'
            f'The ticket is now back on your radar.\r\n\r\n'
            "— Seven's Swarm"
        )
        send_reply(
            to_address=s['sender_email'],
            subject=f'[Swarm] Snooze expired: {ticket_number}',
            body=body
        )
        discord_notify.notify_snooze_fired(ticket_number, note)
        mark_snooze_fired(s['id'])
        print(f'[Tasks] Snooze fired: {ticket_number}')


def check_sla(hours=4):
    """
    Warn Ghost about tickets that have been open longer than `hours` hours.
    Only fires once per ticket (checks activity_log to avoid repeat alerts).
    """
    from database import get_overdue_tickets, get_connection, log_activity
    from email_handler import send_reply
    from config import GHOST_EMAIL
    import discord_notify

    overdue = get_overdue_tickets(hours=hours)
    if not overdue:
        return

    # Filter out tickets already warned about
    conn = get_connection()
    for t in overdue:
        tn = t['ticket_number']
        already = conn.execute(
            "SELECT id FROM activity_log WHERE service='tasks' AND event='sla_warned' AND detail LIKE ?",
            (f'{tn}%',)
        ).fetchone()
        if already:
            continue

        body = (
            f'SLA warning: {tn} has been open for more than {hours} hours.\r\n\r\n'
            f'From:    {t["sender_email"]}\r\n'
            f'Opened:  {t["created_at"]}\r\n'
            f'Question: {(t["question"] or "")[:200]}\r\n\r\n'
            f'You can force-close or resend from the dashboard.\r\n\r\n'
            "— Seven's Swarm"
        )
        send_reply(
            to_address=GHOST_EMAIL,
            subject=f'[Swarm] SLA warning: {tn} open >{hours}h',
            body=body
        )
        discord_notify.notify_sla_warning(
            tn, t['sender_email'], t['created_at'], t['question'] or '', hours
        )
        log_activity('tasks', 'sla_warned', f'{tn} — open >{hours}h')
        print(f'[Tasks] SLA warning sent for {tn}')
    conn.close()


def send_daily_digest():
    """
    Send Ghost a daily summary of swarm activity — email + Discord.
    """
    from database import get_digest_stats, log_activity
    from email_handler import send_reply
    from config import GHOST_EMAIL
    from datetime import date
    import discord_notify

    stats = get_digest_stats()
    today = str(date.today())

    duck_total = stats['duck_yes'] + stats['duck_no']
    duck_rate  = f"{100 * stats['duck_yes'] // duck_total}%" if duck_total else 'n/a'

    tag_line = ''
    if stats['top_tags']:
        tag_line = 'Top tags (7 days): ' + ', '.join(f'{t}({c})' for t, c in stats['top_tags']) + '\r\n'

    body = (
        f"Seven's Swarm — Daily Digest {today}\r\n"
        f"{'=' * 40}\r\n\r\n"
        f"Last 24 hours:\r\n"
        f"  Tickets opened : {stats['opened']}\r\n"
        f"  Tickets closed : {stats['closed']}\r\n"
        f"  Currently open : {stats['open']}\r\n"
        f"  Duck pass rate : {duck_rate} ({stats['duck_yes']} yes / {stats['duck_no']} no)\r\n\r\n"
        + (tag_line + '\r\n' if tag_line else '') +
        "— Seven's Swarm"
    )
    send_reply(
        to_address=GHOST_EMAIL,
        subject=f"[Swarm] Daily digest — {today}",
        body=body
    )
    discord_notify.send_digest(stats, today)
    log_activity('tasks', 'digest_sent', today)
    print(f'[Tasks] Daily digest sent.')


def check_proposals():
    """
    Scan sandpits/shared/proposals/ for new proposal files.
    For each new proposal, notify Ghost via email + Discord.
    A proposal is 'new' if it has no matching activity_log 'proposal_notified' entry.
    """
    from database import get_connection, log_activity
    from sandpits import list_proposals, read_proposal
    from agent_email_ghost import notify_proposal_ready

    proposals = list_proposals()
    if not proposals:
        return

    conn = get_connection()
    for p in proposals:
        fname = p['filename']
        already = conn.execute(
            "SELECT id FROM activity_log WHERE service='tasks' AND event='proposal_notified' AND detail=?",
            (fname,)
        ).fetchone()
        if already:
            continue

        content = read_proposal(fname)
        if not content:
            continue

        notify_proposal_ready(p['agent'], fname, content)
        log_activity('tasks', 'proposal_notified', fname)
        print(f'[Tasks] Proposal notification sent: {fname}')
    conn.close()


def run_play_time():
    """
    Give idle agents their play time — let them draft improvement proposals.
    Checks all working agents (gemma/llama/qwen/eight) for idle status.
    Sniffles audits each draft before it reaches the proposals/ folder.
    Called by the housekeeping scheduler — do not run while queue is active.
    """
    from agent_proposals import run_all_idle_agents
    from queue_manager import get_queue_depth
    depth = get_queue_depth()
    if depth > 0:
        print(f'[Tasks] Play time skipped — queue depth {depth}.')
        return
    results = run_all_idle_agents()
    for agent, ok, msg in results:
        print(f'[Tasks] Play time {agent}: {"OK" if ok else "skip"} — {msg}')
    check_proposals()


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'digest':
        send_daily_digest()
    elif cmd == 'sla':
        check_sla()
    elif cmd == 'snooze':
        check_snoozed()
    elif cmd == 'proposals':
        check_proposals()
    elif cmd == 'playtime':
        run_play_time()
    else:
        print('Usage: swarm_tasks.py [digest|sla|snooze|proposals|playtime]')
