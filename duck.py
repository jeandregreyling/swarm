"""
duck.py — Seven's Swarm Sanity Checker
Clean version for the useful build phase.
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
from logging_bridge import log_action, log_ticket_lifecycle
from database import get_connection, save_memory
from config import GHOST_EMAIL
from email_handler import send_reply
from datetime import datetime
import random

DUCK_CHEERS = [
    'Queue cleared. Everyone did well. The Duck approves. 🦆',
    'All tickets closed. Clean sweep. Quack. 🦆',
    'Empty queue. The Duck is pleased with your work today. 🦆',
    'Queue at zero. The Duck has inspected and found nothing to complain about. 🦆',
]

def _pick_cheer():
    """Pick a random cheer from the list."""
    return random.choice(DUCK_CHEERS)

def _log_to_duck_log(ticket_number, question, result, verdict, cheer=''):
    """Log Duck's verdict to duck_log table."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO duck_log (ticket_number, question, result, verdict, note)
               VALUES (?, ?, ?, ?, ?)""",
            (ticket_number, question[:100], result, verdict, cheer)
        )
        conn.commit()
    finally:
        conn.close()

def duck_check(question, answer):
    """Simple YES/NO sanity check."""
    if not answer or len(answer) < 10:
        return "NO"
    if "Murray River" in answer and "longest" in answer.lower():
        return "NO"
    if "I estimate" in answer or "I think" in answer:
        return "NO"
    return "YES"

def on_ticket_closed(ticket_number, question, final_answer, sender_email):
    """Called by librarian_close() — Duck checks the answer before ticket closes."""
    print(f'[Duck] Sanity checking {ticket_number}...')
    result = duck_check(question, final_answer)
    log_action('duck', f'check:{ticket_number}', f'Result: {result}', 'info')
    log_ticket_lifecycle(ticket_number, 'duck_check', 'Duck', f'Verdict: {result}')
    _log_to_duck_log(ticket_number, question, result, 'YES' if result == 'YES' else 'NO')
    print(f'[Duck] {ticket_number}: {result}')
    return result

def on_queue_clear():
    """Called when queue becomes empty. Celebrate! Log morale."""
    cheer = _pick_cheer()
    print(f'\n[Duck] Queue is clear! {cheer}')

    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM tickets WHERE DATE(closed_at)=DATE('now')").fetchone()[0]
        flagged = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO' AND DATE(created_at)=DATE('now')").fetchone()[0]
    finally:
        conn.close()

    # Log the queue clear to duck_log so Duck can read it next time
    _log_to_duck_log('QUEUE-CLEAR', 'queue cleared', cheer, 'CLEAR', cheer)

    # Notify agents via shared memory
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
    print("Duck sanity checker loaded.")