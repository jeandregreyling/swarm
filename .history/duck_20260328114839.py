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
    print(f'[Duck] {ticket_number}: {result}')
    return result

if __name__ == '__main__':
    print("Duck sanity checker loaded.")