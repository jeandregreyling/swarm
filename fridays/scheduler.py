"""
scheduler.py — Seven's Swarm Scheduler
Basic proactive tasks. Runs daily digest, snooze checks, etc.
"""

import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta
import sys

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)
_utils = os.path.join(_SWARM_ROOT, 'utils')
if _utils not in sys.path:
    sys.path.insert(0, _utils)

from database import get_digest_stats, get_due_snoozed, mark_snooze_fired, get_overdue_tickets, get_connection
from sandpits import list_proposals


def _is_sqlite_lock(exc):
    return isinstance(exc, sqlite3.OperationalError) and 'locked' in str(exc).lower()


def list_tasks():
    """Return all enabled scheduled tasks from the DB."""
    with closing(get_connection()) as conn:
        rows = conn.execute(
            'SELECT id, name, schedule, action_type, action_data, next_run FROM scheduled_tasks WHERE enabled=1 ORDER BY id'
        ).fetchall()
    return [{'id': r[0], 'name': r[1], 'schedule': r[2], 'action_type': r[3], 'action_data': r[4], 'next_run': r[5]} for r in rows]


def compute_next_run(schedule, *, now=None):
    """Compute the next run timestamp for supported Tasker schedules."""
    schedule = (schedule or '').strip()
    now = now or datetime.now()
    s = schedule.lower()
    next_run = None
    if s.startswith('daily '):
        try:
            hhmm = schedule.split(None, 1)[1]
            h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            next_run = candidate.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    elif s.startswith('weekly '):
        try:
            parts = schedule.split(None, 2)  # weekly MON 09:00
            day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
            target_day = day_map.get(parts[1].lower()[:3], 0)
            hhmm = parts[2] if len(parts) > 2 else '09:00'
            h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            candidate += timedelta(days=days_ahead)
            next_run = candidate.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    elif s.startswith('monthly '):
        try:
            parts = schedule.split(None, 2)  # monthly 1 09:00
            day_of_month = int(parts[1])
            hhmm = parts[2] if len(parts) > 2 else '09:00'
            h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
            candidate = now.replace(day=min(day_of_month, 28), hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                month = now.month + 1
                year = now.year
                if month > 12:
                    month = 1
                    year += 1
                candidate = candidate.replace(year=year, month=month)
            next_run = candidate.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    elif s == 'hourly':
        candidate = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        next_run = candidate.strftime('%Y-%m-%d %H:%M:%S')
    elif s.startswith('interval '):
        try:
            val = int(s.split(None, 1)[1].rstrip('m'))
            candidate = now + timedelta(minutes=val)
            next_run = candidate.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    return next_run


def add_task(name, schedule, action_type, action_data, created_by='system'):
    """Add or refresh a scheduled task by name and return its id."""
    next_run = compute_next_run(schedule)
    with closing(get_connection()) as conn:
        row = conn.execute(
            'SELECT id FROM scheduled_tasks WHERE name=? ORDER BY id DESC LIMIT 1',
            (name,),
        ).fetchone()
        if row:
            task_id = row[0]
            conn.execute(
                '''UPDATE scheduled_tasks
                   SET schedule=?, action_type=?, action_data=?, created_by=?,
                       next_run=COALESCE(?, next_run), enabled=1
                   WHERE id=?''',
                (schedule, action_type, action_data, created_by, next_run, task_id),
            )
            conn.execute('DELETE FROM scheduled_tasks WHERE name=? AND id<>?', (name, task_id))
            return task_id
        cur = conn.execute(
            '''INSERT INTO scheduled_tasks
               (name, schedule, action_type, action_data, created_by, next_run, enabled)
               VALUES (?, ?, ?, ?, ?, ?, 1)''',
            (name, schedule, action_type, action_data, created_by, next_run),
        )
        return cur.lastrowid


def _advance_next_run(name):
    """Advance next_run for a task after it fires. Supports daily, weekly, monthly, hourly, interval."""
    with closing(get_connection()) as conn:
        row = conn.execute(
            'SELECT schedule FROM scheduled_tasks WHERE name=?', (name,)
        ).fetchone()
        if not row:
            return
        schedule = (row[0] or '').strip()
        now = datetime.now()
        next_run = compute_next_run(schedule, now=now)
        if next_run:
            conn.execute(
                'UPDATE scheduled_tasks SET last_run=?, next_run=? WHERE name=?',
                (now.strftime('%Y-%m-%d %H:%M:%S'), next_run, name)
            )


def run_daily_brief():
    """Generate a Ghost Brief and email it to Ghost."""
    try:
        _lib_email = os.path.join(_SWARM_ROOT, 'lib/email')
        if _lib_email not in sys.path:
            sys.path.insert(0, _lib_email)
        from brief_engine import generate_brief
        brief = generate_brief(trigger='daily_schedule')
        if not brief:
            print('[Scheduler] Daily brief: generation failed — check Claude API key')
            return
        from email_handler import send_reply
        from config import GHOST_EMAIL
        send_reply(
            to_address=GHOST_EMAIL,
            subject=f'[Swarm] Ghost Brief — {datetime.now().strftime("%A %d %B")}',
            body=brief['content'] + f'\r\n\r\n---\nGenerated by Nine · {brief["tokens_used"]} tokens'
        )
        print(f'[Scheduler] Daily brief sent — {brief["tokens_used"]} tokens')
        _advance_next_run('daily_brief')
    except Exception as e:
        print(f'[Scheduler] Daily brief error: {e}')


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
    _advance_next_run('daily_digest')

def check_snoozed():
    due = get_due_snoozed()
    for snooze in due:
        print(f"[Scheduler] Waking snoozed ticket {snooze['ticket_number']}")
        mark_snooze_fired(snooze['id'])

def disable_task(task_id):
    """Disable a scheduled task by numeric ID."""
    with closing(get_connection()) as conn:
        conn.execute('UPDATE scheduled_tasks SET enabled=0 WHERE id=?', (task_id,))


def parse_schedule_command(line):
    """
    Parse a SCHEDULE command from an email/message line.
    Format: SCHEDULE <schedule> <ACTION_TYPE> <data>
    Examples:
      SCHEDULE daily 09:00 QUESTION What is today's news?
      SCHEDULE daily 18:00 SHELL df -h

    Returns (name, schedule, action_type, action_data) or None if unparseable.
    """
    parts = line.strip().split(None, 3)
    # Expect: SCHEDULE  <word> <HH:MM> <ACTION> <data>   (4+ parts after split)
    # Or:     SCHEDULE  <word> <ACTION> <data>            (3+ parts)
    if len(parts) < 4:
        return None
    # parts[0] is 'SCHEDULE'
    # Try 'daily HH:MM' as the schedule field
    if parts[1].lower() == 'daily' and ':' in parts[2]:
        schedule = f'daily {parts[2]}'
        remainder = parts[3] if len(parts) > 3 else ''
        rem_parts = remainder.split(None, 1)
        if not rem_parts:
            return None
        action_type = rem_parts[0].upper()
        action_data = rem_parts[1] if len(rem_parts) > 1 else ''
    else:
        # Fallback: parts[1]=action_type, rest=data, no schedule
        return None
    name = f'{action_type.lower()}_{schedule.replace(" ", "_").replace(":", "")}'
    return (name, schedule, action_type, action_data)


def check_due():
    """Check for scheduled tasks that are due and run them.

    2026-05-02 (S-28178F1EF6) — Hardened against duplicate fires by acquiring
    a short-lived lease on each due row before execution. Workers from other
    processes will see ``lease_owner != ''`` and skip the row.
    """
    import os
    import shlex
    import subprocess
    from datetime import datetime
    owner = f'sched-{os.getpid()}'
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with closing(get_connection()) as conn:
            cols = {row[1] for row in conn.execute(
                "PRAGMA table_info(scheduled_tasks)").fetchall()}
            has_lease = 'lease_owner' in cols and 'lease_expires_at' in cols
            if has_lease:
                # Claim exactly one due row per scheduler tick. Local agents run on a
                # small machine; claiming every overdue row makes later tasks appear
                # stuck behind the first long local model call.
                row = conn.execute(
                    """SELECT id FROM scheduled_tasks
                       WHERE enabled=1
                         AND (next_run IS NULL OR next_run <= ?)
                         AND (COALESCE(lease_owner,'')=''
                              OR COALESCE(lease_expires_at,'') < ?)
                       ORDER BY
                         CASE name
                           WHEN 'watchdog_deos_cycle' THEN 0
                           WHEN 'local_agent_work_cycle' THEN 1
                           ELSE 2
                         END,
                         COALESCE(next_run, '0000-00-00 00:00:00') ASC,
                         id ASC
                       LIMIT 1""",
                    (now_str, now_str),
                ).fetchone()
                if row:
                    conn.execute(
                        """UPDATE scheduled_tasks
                           SET lease_owner=?, lease_expires_at=datetime('now', '+30 minutes')
                           WHERE id=?
                             AND enabled=1
                             AND (COALESCE(lease_owner,'')=''
                                  OR COALESCE(lease_expires_at,'') < ?)""",
                        (owner, row[0], now_str),
                    )
                    conn.commit()
                rows = conn.execute(
                    """SELECT id, name, action_type, action_data FROM scheduled_tasks
                       WHERE enabled=1 AND lease_owner=?
                       ORDER BY id ASC
                       LIMIT 1""",
                    (owner,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, name, action_type, action_data FROM scheduled_tasks
                       WHERE enabled=1 AND (next_run IS NULL OR next_run <= ?)
                       ORDER BY
                         CASE name
                           WHEN 'watchdog_deos_cycle' THEN 0
                           WHEN 'local_agent_work_cycle' THEN 1
                           ELSE 2
                         END,
                         COALESCE(next_run, '0000-00-00 00:00:00') ASC,
                         id ASC
                       LIMIT 1""",
                    (now_str,)
                ).fetchall()
    except Exception as exc:
        if _is_sqlite_lock(exc):
            print(f'[Scheduler] skipped due check: sqlite lock: {exc}')
            return
        raise

    for row in rows:
        task_id, name, action_type, action_data = row[0], row[1], row[2], row[3]
        try:
            if action_type.upper() == 'SHELL':
                subprocess.Popen(shlex.split(action_data))
                print(f'[Scheduler] Fired SHELL task #{task_id}: {action_data[:60]}')
            elif action_type.upper() == 'PYTHON':
                from fridays.task_runner import run_task
                parts = shlex.split(action_data.strip())
                task_name = parts[0] if parts else ''
                task_args = ' '.join(shlex.quote(p) for p in parts[1:])
                success, output = run_task(task_name, args=task_args)
                status = '✓' if success else '✗'
                print(f'[Scheduler] {status} PYTHON task #{task_id} ({name}): {output[:80]}')
            elif action_type.upper() in ('QUESTION', 'BRIEF'):
                if 'brief_engine' in (action_data or ''):
                    subprocess.Popen(shlex.split(action_data))
                    print(f'[Scheduler] Fired BRIEF task #{task_id}')
            # Advance next_run for this task
            _advance_next_run(name)
        except Exception as e:
            print(f'[Scheduler] Task #{task_id} ({name}) error: {e}')
        finally:
            # Always release lease so the row is eligible for the next due cycle.
            if has_lease:
                try:
                    with closing(get_connection()) as conn:
                        conn.execute(
                            "UPDATE scheduled_tasks SET lease_owner='', "
                            "lease_expires_at='' WHERE id=? AND lease_owner=?",
                            (task_id, owner)
                        )
                        conn.commit()
                except Exception:
                    pass


def main_loop():
    print("Scheduler started — checking every 60 seconds (press Ctrl+C to stop)")
    
    # Initialize Time Wizard session on startup
    try:
        import sys
        _core = os.path.join(_SWARM_ROOT, 'core')
        if _core not in sys.path:
            sys.path.insert(0, _core)
        from time_machine import time_wizard
        session_id = time_wizard.bootstrap_session()
        if session_id:
            print(f"[TimeMachine] Session {session_id} started")
    except Exception as e:
        print(f"[TimeMachine] Initialization warning: {e}")
    
    while True:
        try:
            check_due()
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
