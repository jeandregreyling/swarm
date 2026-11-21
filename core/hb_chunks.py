"""Chunks: HB breaks each task into small pieces and gives APEX ONE at a time (Practice 216; JD 21 Nov 2026: "an entire task is being
handled as a whole instead of homework and HB breaking it down into more manageable chunks for apex").

  plan(text)          split a step's own instructions into 2-8 chunks: its "Do:" sequence, else numbered/bulleted lines, else sentences
  ensure(conn, task)  the task's chunks, made from its Studio step (or objective) the first time
  advance(conn, task) a chunk is done when real progress was recorded after it started (a change, a note, a passing check)
  focus(conn, task)   the card line: "Work ONLY on chunk 2 of 5: ... Done so far: ... Next after this: ..."
  /chunks T-xxx [add <text> | done | reset]   see or steer a task's chunks (JD, HB, Telegram)
Finished chunks stay in hb_chunks (and the task's events), so APEX's card carries one chunk, not the whole task."""
import re
import time

DO = re.compile(r'\bDo:\s*(.+)$', re.M | re.I)   # Practice 217: prepared steps say '... change set. Do: ...' mid-line
ITEM = re.compile(r'^\s*(?:\d+[.)]|[-*\u2022])\s+(.+)$', re.M)
SKIP = re.compile(r'^\s*(?:Done when|HB extra tools|HB restart after|PREPARED|Owner\b|JD\b)', re.I)
PROGRESS = ("kind IN ('mutation','studio_note','studio_task') OR (kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass')")


def table(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_chunks(task_id TEXT, n INTEGER, text TEXT, state TEXT, started_event INTEGER, '
                 'updated_at REAL, PRIMARY KEY(task_id, n))')


def plan(text, most=8):
    """2-8 chunks from a step's instructions, or [] when it is one piece already."""
    text = str(text or '')
    m = DO.search(text)
    if m:
        parts = [p.strip(' .') for p in re.split(r',\s*then\s+|;\s*then\s+|\s+then\s+|,\s+|;\s+|\s*->\s*', m.group(1)) if p.strip(' .')]
    else:
        parts = [p.strip() for p in ITEM.findall(text)]
        if len(parts) < 2:
            body = ' '.join(l for l in text.splitlines()[1:] if l.strip() and not SKIP.match(l))
            parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', body) if len(s.strip()) > 12]
    parts = [p[:300] for p in parts if p and not SKIP.match(p)]
    return parts[:most] if len(parts) >= 2 else []


def _progress(conn, task_id):
    return conn.execute(f'SELECT COALESCE(MAX(event_id),0) FROM hb_task_events WHERE task_id=? AND ({PROGRESS})', (task_id,)).fetchone()[0]


def ensure(conn, task):
    table(conn)
    rows = conn.execute('SELECT n, text, state FROM hb_chunks WHERE task_id=? ORDER BY n', (task['task_id'],)).fetchall()
    if rows:
        return rows
    source = task.get('objective') or ''
    if task.get('step_id'):
        try:
            row = conn.execute('SELECT title, description FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone()
            if row:
                source = f'{row[0]}\n{row[1] or ""}'
        except Exception:
            pass
    parts = plan(source)
    start = _progress(conn, task['task_id'])
    for n, text in enumerate(parts, 1):
        conn.execute('INSERT OR IGNORE INTO hb_chunks VALUES (?,?,?,?,?,?)',
                     (task['task_id'], n, text, 'doing' if n == 1 else 'todo', start if n == 1 else None, time.time()))
    return conn.execute('SELECT n, text, state FROM hb_chunks WHERE task_id=? ORDER BY n', (task['task_id'],)).fetchall()


def advance(conn, task):
    """Mark the current chunk done when progress was recorded after it started; start the next. Returns the chunk number done, or None."""
    table(conn)
    cur = conn.execute("SELECT n, started_event FROM hb_chunks WHERE task_id=? AND state='doing' ORDER BY n LIMIT 1", (task['task_id'],)).fetchone()
    if not cur:
        return None
    now = _progress(conn, task['task_id'])
    if now <= (cur[1] or 0):
        return None
    conn.execute("UPDATE hb_chunks SET state='done', updated_at=? WHERE task_id=? AND n=?", (time.time(), task['task_id'], cur[0]))
    conn.execute("UPDATE hb_chunks SET state='doing', started_event=?, updated_at=? WHERE task_id=? AND n=(SELECT MIN(n) FROM hb_chunks "
                 "WHERE task_id=? AND state='todo')", (now, time.time(), task['task_id'], task['task_id']))
    return cur[0]


def focus(conn, task, writer=None):
    """The line for APEX's card, or '' when the task has no chunks. Practice 217: with writer (a connect function) the chunks are
    saved on their own connection and committed - the card is built inside a transaction nobody commits, so they vanished."""
    # Practice 218: never open the writer while conn already holds a write transaction (peer inbox: authenticate wrote) -
    # the second connection waited 30 s on its own request's lock on every poll and locked HB's database. That caller commits itself.
    if writer is not None and not getattr(conn, 'in_transaction', False):
        import sqlite3
        from contextlib import closing
        with closing(writer()) as w:
            w.execute('PRAGMA busy_timeout=3000')   # Practice 218: a busy database costs this card its chunk line, never 30 s of lock
            try:
                line = focus(w, task)
                w.commit()
            except sqlite3.OperationalError:
                w.rollback()
                return ''
        return line
    rows = ensure(conn, task)
    if not rows:
        return ''
    advance(conn, task)
    rows = conn.execute('SELECT n, text, state FROM hb_chunks WHERE task_id=? ORDER BY n', (task['task_id'],)).fetchall()
    total = len(rows)
    doing = next((r for r in rows if r[2] == 'doing'), None)
    done = [r for r in rows if r[2] == 'done']
    if not doing:
        return f"All {total} chunks of this task are done - run the step's own check and report the receipts."
    nxt = next((r for r in rows if r[2] == 'todo'), None)
    return (f"HB CHUNK - work ONLY on chunk {doing[0]} of {total}: {doing[1]}\n"
            f"Finish it with your tools in this turn and stop; HB gives you the next chunk."
            + (f"\nDone so far: " + '; '.join(f'{r[0]}. {r[1][:80]}' for r in done) if done else '')
            + (f"\nNext after this: {nxt[1][:120]}" if nxt else "\nThis is the last chunk: then run the step's own check."))


def command(conn, args, actor):
    """/chunks T-xxx [add <text> | done | reset]"""
    if not args:
        return 'Use /chunks T-xxxx to see a task\'s chunks; /chunks T-xxxx add <text> | done | reset.'
    from core import hb_tasks
    task = hb_tasks.get(conn, args[0].upper())
    if not task:
        return f'No task {args[0]}.'
    table(conn)
    sub = args[1].lower() if len(args) > 1 else ''
    if sub == 'reset':
        conn.execute('DELETE FROM hb_chunks WHERE task_id=?', (task['task_id'],))
    elif sub == 'add' and len(args) > 2:
        n = (conn.execute('SELECT COALESCE(MAX(n),0) FROM hb_chunks WHERE task_id=?', (task['task_id'],)).fetchone()[0]) + 1
        conn.execute('INSERT INTO hb_chunks VALUES (?,?,?,?,?,?)', (task['task_id'], n, ' '.join(args[2:])[:300], 'todo', None, time.time()))
        if not conn.execute("SELECT 1 FROM hb_chunks WHERE task_id=? AND state='doing'", (task['task_id'],)).fetchone():
            conn.execute("UPDATE hb_chunks SET state='doing', started_event=? WHERE task_id=? AND n=?", (_progress(conn, task['task_id']), task['task_id'], n))
    elif sub == 'done':
        conn.execute("UPDATE hb_chunks SET started_event=-1 WHERE task_id=? AND state='doing'", (task['task_id'],))
        advance(conn, task)
    rows = ensure(conn, task)
    if not rows:
        return f"{task['task_id']} is one piece (no chunks). /chunks {task['task_id']} add <text> adds one."
    mark = {'done': '✓', 'doing': '▶', 'todo': '·'}
    return f"Chunks of {task['task_id']} ({task.get('title') or ''}):\n" + '\n'.join(f"{mark.get(s, '·')} {n}. {t}" for n, t, s in rows)
