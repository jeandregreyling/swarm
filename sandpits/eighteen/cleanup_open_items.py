#!/usr/bin/env python3
import sqlite3
import datetime

DB = './swarm_memory.db'
conn = sqlite3.connect(DB)
c = conn.cursor()
now = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')

log = []


def close_work_proposals(where_clause, reason):
    c.execute(f"SELECT id FROM work_proposals WHERE {where_clause};")
    rows = c.fetchall()
    ids = [str(r[0]) for r in rows]
    if not ids:
        return 0
    placeholders = ','.join('?' * len(ids))
    c.execute(
        f"UPDATE work_proposals SET status='closed', updated_at=? WHERE id IN ({placeholders});",
        [now] + ids
    )
    log.append(f"CLOSED {len(ids)} work_proposals: {reason}")
    return len(ids)


# 1. Close loop artifacts
artifact_titles = [
    'App build \u00b7 Y50App \u2192 ios',
    'App build \u00b7 TestApp \u2192 android',
    'Media job \u00b7 musicgen',
    'App build \u00b7 app-draft \u2192 ios',
    'App build \u00b7 app-active \u2192 ios',
    'App build \u00b7 app-paused \u2192 ios',
    'App build \u00b7 Y50App \u2192 android',
    'seed for note tests',
    '(promoted)',
]
total_closed = 0
for title in artifact_titles:
    total_closed += close_work_proposals(
        f"status IN ('pending','queued') AND title = '{title}'",
        f"artifact loop: {title[:40]}"
    )

# 2. Close stale approved/in-progress
total_closed += close_work_proposals(
    "status IN ('approved','in_progress') AND created_at < '2026-05-03'",
    "stale >7 days"
)

# 3. Close duplicate VOICE Cybersecurity pending
total_closed += close_work_proposals(
    "status='pending' AND agent='user_seven' AND title LIKE '%Cybersecurity + VPN%'",
    "duplicate of queued"
)

# 4. Abandon queued queue app-build artifacts
c.execute("""
    SELECT id FROM queue
    WHERE status='queued' AND agent='ghost_coder' AND subject LIKE 'App build%'
""")
queue_ids = [str(r[0]) for r in c.fetchall()]
if queue_ids:
    placeholders = ','.join('?' * len(queue_ids))
    c.execute(
        f"UPDATE queue SET status='abandoned', completed_at=? WHERE id IN ({placeholders});",
        [now] + queue_ids
    )
    log.append(f"ABANDONED {len(queue_ids)} queue items: app-build artifacts")

# 5. Close stale queued video renders
c.execute(
    "UPDATE video_render_jobs SET status='failed', updated_at=? WHERE status='queued' AND created_at < '2026-05-03';",
    (now,)
)
log.append(f"CLOSED stale video renders: {c.rowcount}")

# 6. Close stale open ticket
c.execute(
    "UPDATE tickets SET status='closed', closed_at=? WHERE status='open' AND created_at < '2026-05-03';",
    (now,)
)
log.append(f"CLOSED stale tickets: {c.rowcount}")

conn.commit()

# Count remaining
c.execute("SELECT status, COUNT(*) FROM work_proposals WHERE status IN ('pending','approved','in_progress','todo','uat','queued') GROUP BY status;")
remaining_proposals = c.fetchall()
c.execute("SELECT COUNT(*) FROM project_steps WHERE status != 'done';")
remaining_steps = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM queue WHERE status='queued';")
remaining_queue = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM tickets WHERE status='open';")
remaining_tickets = c.fetchone()[0]

conn.close()

print("=" * 60)
print("CLEANUP COMPLETE")
for entry in log:
    print(f"  {entry}")
print()
print(f"Remaining proposals: {remaining_proposals}")
print(f"Remaining project steps: {remaining_steps}")
print(f"Remaining queued items: {remaining_queue}")
print(f"Remaining open tickets: {remaining_tickets}")
print("=" * 60)