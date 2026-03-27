"""
scheduler.py — Seven's Swarm Scheduler
Basic proactive tasks. Runs daily digest, snooze checks, etc.
"""

import time
from datetime import datetime
import sys
sys.path.insert(0, '/home/seven/swarm')

from database import get_digest_stats, get_due_snoozed, mark_snooze_fired, get_overdue_tickets
from sandpits import list_proposals

def run_daily_digest():
    stats = get_digest_stats()
    proposals = len(list_proposals())
    overdue = len(get_overdue_tickets(hours=4))

    print(f"\n[Scheduler] Daily Digest — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Tickets opened today: {stats['opened']}")
    print(f"  Tickets closed today: {stats['closed']}")
    print(f"  Open tickets: {stats['open']}")
    print(f"  Overdue tickets (>4h): {overdue}")
    print(f"  Pending proposals: {proposals}")
    print(f"  Duck checks: YES {stats['duck_yes']} | NO {stats['duck_no']}")
    if stats['top_tags']:
        print("  Top tags:", [t[0] for t in stats['top_tags']])

def check_snoozed():
    due = get_due_snoozed()
    for snooze in due:
        print(f"[Scheduler] Waking snoozed ticket {snooze['ticket_number']}")
        mark_snooze_fired(snooze['id'])

def main_loop():
    print("Scheduler started — checking every 60 seconds (press Ctrl+C to stop)")
    while True:
        try:
            run_daily_digest()
            check_snoozed()
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
            break
        except Exception as e:
            print(f"[Scheduler Error] {e}")
            time.sleep(60)

if __name__ == '__main__':
    main_loop()