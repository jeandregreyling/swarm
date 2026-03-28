"""
duck.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Sanity checker. Runs after every ticket close. No exceptions.

YES → ticket passes, logged to duck_log, Librarian closes.
NO  → ticket flagged, Sniffles called when queue is quiet.

Duck reads its own history (duck_log) so it doesn't repeat jokes.
Duck writes a weekly morale report to Ghost from that log.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
from database import get_connection
from config import GHOST_EMAIL
from email_handler import send_reply
import ollama
from datetime import datetime
import random
import subprocess

DUCK_MODEL = 'qwen:latest'

DUCK_CHEERS = [
    'Queue cleared. Everyone did well. The Duck approves. 🦆',
    'All tickets closed. Clean sweep. Quack. 🦆',
    'Empty queue. The Duck is pleased with your work today. 🦆',
    'Queue at zero. The Duck has inspected and found nothing to complain about. 🦆',
    'All done. The Duck would buy you all a coffee if ducks could hold cups. 🦆',
    'Tickets closed. Memories indexed. The Duck nods approvingly. 🦆',
    'Nothing left in the queue. The Duck has waddled off for a well-earned rest. 🦆',
    'Queue empty. The agents did their best. The Duck is satisfied. 🦆',
]


def _get_used_cheers():
    """Duck reads its own history to avoid repeating the same sign-off."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT reason FROM duck_log WHERE result='CLEAR' ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return set(r[0] for r in rows if r[0])


def _pick_cheer():
    used = _get_used_cheers()
    fresh = [c for c in DUCK_CHEERS if c not in used]
    pool  = fresh if fresh else DUCK_CHEERS
    return random.choice(pool)


def _log_to_duck_log(ticket_number, question, answer, result, reason=''):
    """Write every sanity check result to duck_log. No exceptions."""
    conn = get_connection()
    ticket_row = conn.execute("SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
    ticket_id = ticket_row['id'] if ticket_row else None
    conn.execute(
        """INSERT INTO duck_log (ticket_id, ticket_number, question, answer, result, reason)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ticket_id, ticket_number, question[:300], answer[:300], result, reason[:500])
    )
    conn.commit()
    conn.close()


def _update_ticket_duck_result(ticket_number, result, reason=''):
    """Write Duck's verdict onto the ticket record."""
    conn = get_connection()
    conn.execute(
        "UPDATE tickets SET duck_result=?, updated_at=datetime('now') WHERE ticket_number=?",
        (f'{result}: {reason}'[:500] if reason else result, ticket_number)
    )
    conn.commit()
    conn.close()


def quick_sanity_check(ticket_number, question, answer):
    prompt = (
        'You are a quick fact checker. Read this Q&A and answer only YES or NO then one sentence.\n\n'
        'Question: ' + question + '\n'
        'Answer: ' + answer[:300] + '\n\n'
        'Does this answer make basic factual sense? '
        'Reply: YES [one sentence] or NO [one sentence explaining the problem]'
    )
    response = ollama.chat(
        model=DUCK_MODEL,
        messages=[{'role': 'user', 'content': prompt}],
        options={'temperature': 0.1}
    )
    return response['message']['content'].strip()


def flag_for_sniffles(ticket_number, reason):
    conn = get_connection()
    conn.execute(
        'UPDATE tickets SET sniffles_result=? WHERE ticket_number=?',
        ('DUCK_FLAGGED: ' + reason, ticket_number)
    )
    conn.commit()
    conn.close()
    print(f'[Duck] Flagged {ticket_number} for Sniffles: {reason}')


def run_sniffles_if_needed():
    """Run Sniffles if Duck has flagged tickets and the queue has been quiet for 1+ hour."""
    from queue_manager import is_queue_quiet
    conn = get_connection()
    flagged = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE sniffles_result LIKE 'DUCK_FLAGGED%' AND sniffles_checked=0"
    ).fetchone()[0]
    conn.close()
    if flagged > 0 and is_queue_quiet():
        print(f'[Duck] {flagged} ticket(s) flagged and queue quiet. Calling Sniffles...')
        subprocess.Popen(['python3', '/home/seven/swarm/sniffer.py'])
    elif flagged > 0:
        print(f'[Duck] {flagged} ticket(s) flagged but queue still active. Sniffles will wait.')


def on_ticket_closed(ticket_number, question, answer, sender_email):
    print(f'\n[Duck] Ticket {ticket_number} closed. Running quick sanity check...')
    result = quick_sanity_check(ticket_number, question, answer)
    print(f'[Duck] Sanity check: {result[:80]}')

    passed = not result.upper().startswith('NO')
    label  = 'YES' if passed else 'NO'
    reason = result

    # Log to duck_log — every check, no exceptions
    _log_to_duck_log(ticket_number, question, answer, label, reason)

    # Write Duck's verdict onto the ticket
    _update_ticket_duck_result(ticket_number, label, reason)

    if passed:
        print('[Duck] Sanity check passed. 🦆')
    else:
        flag_for_sniffles(ticket_number, result)
        print('[Duck] Something smells wrong. Flagged for Sniffles.')

    run_sniffles_if_needed()


def on_queue_clear():
    cheer = _pick_cheer()
    print(f'\n[Duck] Queue is clear! {cheer}')

    conn = get_connection()
    count      = conn.execute("SELECT COUNT(*) FROM tickets WHERE DATE(closed_at)=DATE('now')").fetchone()[0]
    flagged    = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO' AND DATE(created_at)=DATE('now')").fetchone()[0]
    conn.close()

    # Log the queue clear to duck_log so Duck can read it next time
    _log_to_duck_log('QUEUE-CLEAR', 'queue cleared', cheer, 'CLEAR', cheer)

    # Notify agents via shared memory
    from database import save_memory
    save_memory(
        'Duck',
        f'Queue cleared {datetime.now().strftime("%Y-%m-%d")}',
        f'{cheer} {count} tickets processed today. {flagged} flagged.',
        tags='duck,morale,queue,cleared',
        importance=3
    )

    body = (
        cheer + '\r\n\r\n'
        f'Tickets processed today: {count}\r\n'
        f'Flagged for Sniffles: {flagged}\r\n'
        f'All sanity checks logged to duck_log.\r\n\r\n'
        '— The Duck 🦆'
    )
    send_reply(
        to_address=GHOST_EMAIL,
        subject=f'[Duck] Queue clear — {datetime.now().strftime("%H:%M")} 🦆',
        body=body
    )
    print('[Duck] Ghost notified. Quack complete.')


if __name__ == '__main__':
    print('Duck test — simulating ticket sanity check...')
    on_ticket_closed(
        'TICKET-TEST',
        'What is the longest river in Australia?',
        'The Murray River at 2,531km is the longest river in Australia.',
        'test@example.com'
    )
    print('\nDuck test — simulating queue clear...')
    on_queue_clear()

