"""Background work in main chat (owner 14 Nov 2026): "if the homework team is running they need to be in main chat so I can see what
they are doing, same rules apply, everything goes through main chat".

The CPU jobs (homework spec cards, counsel reviews, proposal checks) register here while they run. The live activity panel and the holder
show them like any agent, and each posts one line in main chat when it starts and when it finishes.
"""
import threading
import time

_LOCK = threading.Lock()
RUNNING = {}
ROLE = {'homework': 'Homework', 'counsel': 'Counsel', 'proposal': 'HB check'}


def start(kind, task, model, what, conn=None):
    with _LOCK:
        RUNNING[kind] = {'kind': kind, 'role': ROLE.get(kind, kind), 'model': model, 'task_id': task.get('task_id'),
                         'task': str(task.get('title') or '')[:90], 'started': time.time(), 'steps': [{'at': time.strftime('%H:%M'), 'what': what}]}
    if conn is not None:
        _post(conn, task, f"🌱 {ROLE.get(kind, kind)} ({model}) started: {what}")


def step(kind, what):
    with _LOCK:
        if kind in RUNNING:
            RUNNING[kind]['steps'] = (RUNNING[kind]['steps'] + [{'at': time.strftime('%H:%M'), 'what': what}])[-6:]


def finish(kind, conn=None, task=None, outcome=None):
    with _LOCK:
        job = RUNNING.pop(kind, None)
    if conn is not None and task is not None and outcome:
        took = f" ({round((time.time() - job['started']) / 60, 1)} min)" if job else ''
        _post(conn, task, f"{outcome}{took}")


def snapshot():
    with _LOCK:
        return [dict(v, steps=list(v['steps'])) for v in RUNNING.values()]


def _post(conn, task, text):
    """Post on its OWN short connection and commit at once. Bug 14 Nov: posting on the job's connection opened a write transaction that
    stayed open for the whole model call (minutes), locking the database for everyone - the session check timed out and the page kept
    showing "Maintenance". The job's connection is never used for writing here."""
    try:
        import sqlite3
        from contextlib import closing
        from core.hb_plain import message
        cid = task.get('conversation_id') or 2834
        sql = "INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)"
        path = conn.execute('PRAGMA database_list').fetchone()[2] if conn is not None else ''
        if not path:                                   # an in-memory database (tests): nobody else waits on it
            conn.execute(sql, (cid, message(text)))
            return
        with closing(sqlite3.connect(path, timeout=10)) as own, own:   # the same database file, its own short transaction
            own.execute(sql, (cid, message(text)))
    except Exception:
        pass
