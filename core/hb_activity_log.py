"""HB Live L1 (owner 20 Nov 2026: "rule number 1 is that everything should always be visible in main chat ... a live display pulling
everything together"; spec docs/spec-hb-live-dashboard.md). One append-only log of what every worker does, written at the choke points:

  * core/llm.chat_via_gateway  - every local model call: start + finish (model, device, how long, tokens, error)
  * core/apex_tools.run_apex_tools - one run per APEX turn (main chat or workflow), with its step lines (Practice 176 say_step)
  * runtime/claude_helpers/hbrun.py - Claude Code's own work (sweeps, suite runs, change sets)
  * adapters in core/hb_live.py read the records other parts already keep (peer work, admin, background, translator)

Rows: hb_activity_log(id, at, run_id, parent, lane, actor, model, device, task_id, step_id, kind, text, purpose)
  kind: start | step | call | finish | error.  A run is open while it has a start and no finish/error.

Logging never breaks the work it records: every write is best-effort. Under pytest it is off unless a test sets FORCE = True."""
import contextlib
import contextvars
import os
import time
import uuid

FORCE = False
KEEP_DAYS = 7
_RUN = contextvars.ContextVar('hb_activity_run', default=None)      # the open run this thread/task belongs to
LANES = ('gpu', 'cpu', 'online', 'hb', 'admin', 'claude-code', 'system')


def enabled():
    return FORCE or not os.environ.get('PYTEST_CURRENT_TEST')


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_activity_log(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, run_id TEXT, parent TEXT, '
                 'lane TEXT, actor TEXT, model TEXT, device TEXT, task_id TEXT, step_id TEXT, kind TEXT, text TEXT, purpose TEXT)')
    conn.execute('CREATE INDEX IF NOT EXISTS hb_activity_log_run ON hb_activity_log(run_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS hb_activity_log_at ON hb_activity_log(at)')


def _connect():
    from utils.db._connection import get_connection
    return get_connection()


def write(row, conn=None):
    """Insert one event. Returns True when written. Never raises."""
    if not enabled():
        return False
    own = conn is None
    try:
        conn = conn or _connect()
        try:
            ensure(conn)
            conn.execute('INSERT INTO hb_activity_log(at, run_id, parent, lane, actor, model, device, task_id, step_id, kind, text, purpose) '
                         'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                         (row.get('at') or time.time(), row.get('run_id'), row.get('parent'), row.get('lane'), row.get('actor'),
                          row.get('model'), row.get('device'), row.get('task_id'), row.get('step_id'), row.get('kind'),
                          str(row.get('text') or '')[:300], row.get('purpose')))
            if own:
                conn.commit()
        finally:
            if own:
                conn.close()
        return True
    except Exception:
        return False


def who(model):
    """(actor, lane, device, real model name) for a model name as callers pass it."""
    name = str(model or '')
    low = name.lower()
    try:
        from core.hb_apex_swap import playing, backend
        apex_now = playing()
        where = backend()
    except Exception:
        apex_now, where = None, None
    if apex_now and (low == str(apex_now).lower() or low.startswith('gpt-oss') or low.startswith('apex')):
        return 'apex', 'gpu', {'rocm': 'ROCm', 'vulkan': 'Vulkan'}.get(where or '', 'GPU'), apex_now
    if 'fred' in low:
        return 'fred', 'cpu', 'CPU', name
    if any(k in low for k in ('homework', 'translate', 'embed', 'nomic', '0.5b', '1.5b', ':3b', '-3b')):
        return 'small', 'cpu', 'CPU', name
    return 'hb', 'hb', '', name


class Run:
    """An open run; finish() closes it. Used through run() or begin()/end()."""

    def __init__(self, run_id, base):
        self.run_id, self.base, self.closed, self.started = run_id, base, False, time.time()

    def step(self, text, kind='step'):
        write({**self.base, 'run_id': self.run_id, 'kind': kind, 'text': text})

    def finish(self, ok=True, text=''):
        if self.closed:
            return
        self.closed = True
        took = time.time() - self.started
        write({**self.base, 'run_id': self.run_id, 'kind': 'finish' if ok else 'error',
               'text': (text or ('done' if ok else 'failed')) + f' ({took:.0f} s)'})


def begin(actor, lane, title, *, model=None, device=None, task_id=None, step_id=None, purpose=None, run_id=None):
    parent = _RUN.get()
    run = Run(run_id or 'R-' + uuid.uuid4().hex[:10].upper(),
              {'parent': parent.run_id if parent else None, 'lane': lane, 'actor': actor, 'model': model, 'device': device,
               'task_id': task_id or (parent.base.get('task_id') if parent else None),
               'step_id': step_id or (parent.base.get('step_id') if parent else None), 'purpose': purpose})
    write({**run.base, 'run_id': run.run_id, 'kind': 'start', 'text': title})
    return run


@contextlib.contextmanager
def run(actor, lane, title, **kw):
    """with run('apex', 'gpu', 'MCB question', model=..., purpose='main-chat turn') as r: ... r.step('...')"""
    r = begin(actor, lane, title, **kw)
    token = _RUN.set(r)
    try:
        yield r
    except BaseException as exc:
        r.finish(False, f'{type(exc).__name__}: {exc}'[:200])
        raise
    finally:
        _RUN.reset(token)
        r.finish(True)


def current():
    return _RUN.get()


def step(text, kind='step'):
    """A step line for the run this code is inside (no-op outside a run)."""
    r = _RUN.get()
    if r is not None and text:
        r.step(text, kind)


def prune(conn, now=None):
    ensure(conn)
    conn.execute('DELETE FROM hb_activity_log WHERE at < ?', ((now or time.time()) - KEEP_DAYS * 86400,))


def open_runs(conn, since_s=6 * 3600, now=None):
    """Runs with a start and no finish/error in the last since_s seconds: [{run_id, lane, actor, model, ...,'title','at'}]."""
    ensure(conn)
    now = now or time.time()
    rows = conn.execute("SELECT s.run_id, s.parent, s.lane, s.actor, s.model, s.device, s.task_id, s.step_id, s.text, s.at, s.purpose "
                        "FROM hb_activity_log s WHERE s.kind='start' AND s.at >= ? AND NOT EXISTS (SELECT 1 FROM hb_activity_log f "
                        "WHERE f.run_id=s.run_id AND f.kind IN ('finish','error')) ORDER BY s.at", (now - since_s,)).fetchall()
    keys = ('run_id', 'parent', 'lane', 'actor', 'model', 'device', 'task_id', 'step_id', 'title', 'at', 'purpose')
    return [dict(zip(keys, r)) for r in rows]


def trail(conn, run_id, limit=12):
    """The last steps of a run and its child runs, oldest first: [{at, kind, text}]."""
    ensure(conn)
    rows = conn.execute("SELECT at, kind, text FROM hb_activity_log WHERE run_id=? OR parent=? ORDER BY id DESC LIMIT ?",
                        (run_id, run_id, limit)).fetchall()
    return [{'at': a, 'kind': k, 'text': t} for a, k, t in reversed(rows)]


def finished(conn, limit=20):
    """Recently finished top-level runs: [{run_id, lane, actor, model, title, at, took_s, outcome, steps}]."""
    ensure(conn)
    rows = conn.execute("SELECT s.run_id, s.lane, s.actor, s.model, s.text, s.at, f.at, f.kind, f.text, "
                        "(SELECT COUNT(*) FROM hb_activity_log x WHERE (x.run_id=s.run_id OR x.parent=s.run_id) AND x.kind IN ('step','call')) "
                        "FROM hb_activity_log s JOIN hb_activity_log f ON f.run_id=s.run_id AND f.kind IN ('finish','error') "
                        "WHERE s.kind='start' AND s.parent IS NULL ORDER BY f.at DESC LIMIT ?", (limit,)).fetchall()
    return [{'run_id': r[0], 'lane': r[1], 'actor': r[2], 'model': r[3], 'title': r[4], 'at': r[6], 'took_s': round((r[6] or 0) - (r[5] or 0)),
             'outcome': 'ok' if r[7] == 'finish' else 'error', 'last': r[8], 'steps': r[9]} for r in rows]
