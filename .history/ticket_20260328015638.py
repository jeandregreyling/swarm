"""
ticket.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Ticket lifecycle management.

open → (processing) → closed

The Librarian closes every ticket.
The Duck checks every ticket before it closes.
Neither step is optional.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
from system_clock import get_timestamp
from logging_bridge import log_action, log_ticket_lifecycle, batch_commit
import logging

logger = logging.getLogger('seven.ticket')


def create(ticket_number, sender_email, question, tags='', queue_id=None, email_message_id=''):
    """
    Create a ticket and log its queue linkage.
    Called after Librarian intake — ticket is open from this point.
    email_message_id: the Message-ID of the original incoming email, used for
                      thread matching when the sender replies to Seven's response.
    """
    from database import get_connection

    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO tickets
               (ticket_number, queue_id, sender_email, question, tags, status, email_message_id)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
            (ticket_number, queue_id, sender_email, question[:500], tags, email_message_id or '', get_timestamp())
        )
        conn.commit()

        if queue_id:
            ticket_row = conn.execute(
                "SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)
            ).fetchone()
            if ticket_row:
                conn.execute(
                    """INSERT INTO ticket_notes (ticket_id, agent, note_type, content)
                       VALUES (?, 'librarian', 'intake', ?)""",
                    (ticket_row['id'], f'queue_id={queue_id} | tags={tags}')
                )
                conn.commit()
    finally:
        conn.close()

    logger.info(f'[Ticket] Created {ticket_number} for {sender_email}')
    return ticket_number


def set_routing(ticket_number, routing_dict):
    """Store Gemma's FL-001 routing decision on the ticket record."""
    from database import get_connection
    routing_str = ' | '.join(f'{k}={v}' for k, v in routing_dict.items())
    conn = get_connection()
    conn.execute(
        "UPDATE tickets SET gemma_routing=?, updated_at=datetime('now') WHERE ticket_number=?",
        (routing_str, ticket_number)
    )
    conn.commit()
    conn.close()


def add_agent_note(ticket_number, agent, note_type, content, confidence=0.8):
    """Log an agent's contribution to the ticket deliberation."""
    from database import get_connection
    conn = get_connection()
    try:
        ticket = conn.execute(
            "SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)
        ).fetchone()
        if ticket:
            conn.execute(
                """INSERT INTO ticket_notes (ticket_id, agent, note_type, content, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (ticket['id'], agent, note_type, content, confidence)
            )
            conn.commit()
    finally:
        conn.close()


def librarian_close(ticket_number, question, final_answer, queue_id=None, sender_email=None):
    """
    RL-007 — Librarian closes the ticket.

    Step 1: Duck sanity check — YES passes, NO flags for Sniffles.
    Step 2: database.close_ticket() — sets status=closed, sniffles_checked=0.
    Step 3: queue_manager.mark_completed() — queue entry done.

    This function owns the close. Nothing else calls close_ticket directly.
    """
    from database import close_ticket
    from duck import on_ticket_closed
    from queue_manager import mark_completed

    # Step 1: Duck checks the answer
    if sender_email:
        print(f'[Librarian] Calling Duck for {ticket_number}...')
        on_ticket_closed(ticket_number, question, final_answer, sender_email)
    else:
        logger.warning(f'[Librarian] No sender_email for Duck check on {ticket_number}')

    # Step 2: Close the ticket in the database
    close_ticket(ticket_number, final_answer)

    # Step 3: Mark queue entry completed
    if queue_id:
        mark_completed(queue_id)

    logger.info(f'[Librarian] {ticket_number} closed.')
    print(f'[Librarian] Ticket {ticket_number} closed and queued.')
