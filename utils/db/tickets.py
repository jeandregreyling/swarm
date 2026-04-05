"""
db.tickets — Ticket CRUD, snooze, overdue, digest stats.
"""
from ._connection import get_connection


def close_ticket(ticket_number, final_answer):
    conn = get_connection()
    conn.execute("""
        UPDATE tickets SET status='closed', final_answer=?, sniffles_checked=0,
        closed_at=datetime('now'), updated_at=datetime('now')
        WHERE ticket_number=?
    """, (final_answer, ticket_number))
    conn.commit()
    conn.close()


def find_ticket_by_thread(in_reply_to='', references=''):
    """
    Look for an existing ticket whose original email Message-ID appears in the
    incoming email's In-Reply-To or References headers (which contain the full
    thread chain). Returns the ticket row dict, or None.
    """
    combined = (in_reply_to + ' ' + references).strip()
    if not combined:
        return None
    conn = get_connection()
    # Pull all tickets that have a stored email_message_id
    rows = conn.execute(
        "SELECT * FROM tickets WHERE email_message_id != '' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    for row in rows:
        mid = row['email_message_id'].strip()
        if mid and mid in combined:
            return dict(row)
    return None


def reopen_ticket(ticket_number):
    """Re-open a closed ticket for a follow-up reply."""
    conn = get_connection()
    conn.execute(
        "UPDATE tickets SET status='open', closed_at=NULL, updated_at=datetime('now') "
        "WHERE ticket_number=?",
        (ticket_number,)
    )
    conn.commit()
    conn.close()


def update_ticket_tags(ticket_number, new_tags):
    """Append tags to a ticket (space-separated, deduped)."""
    conn = get_connection()
    row = conn.execute("SELECT tags FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
    if not row:
        conn.close()
        return False
    existing = set((row['tags'] or '').split())
    combined = ' '.join(sorted(existing | set(new_tags.split())))
    conn.execute("UPDATE tickets SET tags=?, updated_at=datetime('now') WHERE ticket_number=?",
                 (combined, ticket_number))
    conn.commit()
    conn.close()
    return True


def add_ticket_note_by_number(ticket_number, agent, content, note_type='ghost_note'):
    """Log a note against a ticket by ticket number."""
    conn = get_connection()
    ticket = conn.execute("SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
    if not ticket:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO ticket_notes (ticket_id, agent, note_type, content) VALUES (?,?,?,?)",
        (ticket['id'], agent, note_type, content)
    )
    conn.commit()
    conn.close()
    return True


def snooze_ticket(ticket_number, sender_email, wake_at_iso, note=''):
    """Park a ticket until wake_at_iso (ISO datetime string)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO snoozed_tickets (ticket_number, sender_email, wake_at, note) VALUES (?,?,?,?)",
        (ticket_number, sender_email, wake_at_iso, note)
    )
    conn.commit()
    conn.close()


def get_due_snoozed():
    """Return snoozed tickets whose wake_at time has passed and haven't fired yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM snoozed_tickets WHERE fired=0 AND wake_at <= datetime('now')"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_snooze_fired(snooze_id):
    conn = get_connection()
    conn.execute("UPDATE snoozed_tickets SET fired=1 WHERE id=?", (snooze_id,))
    conn.commit()
    conn.close()


def get_overdue_tickets(hours=4):
    """Return open tickets that have been open longer than `hours` hours."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT ticket_number, sender_email, question, created_at FROM tickets "
        "WHERE status='open' AND created_at <= datetime('now', ?)",
        (f'-{hours} hours',)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_digest_stats():
    """Stats for the daily email digest."""
    conn = get_connection()
    opened  = conn.execute("SELECT COUNT(*) FROM tickets WHERE created_at >= datetime('now','-1 day')").fetchone()[0]
    closed  = conn.execute("SELECT COUNT(*) FROM tickets WHERE closed_at  >= datetime('now','-1 day')").fetchone()[0]
    open_ct = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
    duck_yes = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES' AND created_at >= datetime('now','-1 day')").fetchone()[0]
    duck_no  = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'  AND created_at >= datetime('now','-1 day')").fetchone()[0]
    top_tags = conn.execute(
        "SELECT tags FROM tickets WHERE created_at >= datetime('now','-7 day') AND tags != ''"
    ).fetchall()
    conn.close()
    # Count individual tags
    from collections import Counter
    tag_counts = Counter()
    for row in top_tags:
        for t in (row['tags'] or '').split():
            tag_counts[t] += 1
    return {
        'opened': opened, 'closed': closed, 'open': open_ct,
        'duck_yes': duck_yes, 'duck_no': duck_no,
        'top_tags': tag_counts.most_common(5)
    }
