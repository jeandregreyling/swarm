"""Live activity (owner 14 Nov 2026): plain text of what the models are doing right now, for the strip under the thinking bubble.

snapshot(conn) -> {'running': bool, 'lines': [...]}: one block per running agent turn (who, on what, the stage, how long, and its last
tool calls with their result), then the CPU background jobs (homework, counsel, benchmark). Everything is read from HB's records:
hb_executions, hb_peer_work, hb_task_events and hb_background. Nothing is written."""
import json
import time

WHERE = {'apex': 'GPU', 'fred': 'CPU / RAM'}
KINDS = ('tool_result', 'tool_failure', 'test_result', 'mutation')


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _took(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 60} min {seconds % 60:02d} s' if seconds >= 60 else f'{seconds} s'


def event_line(kind, payload):
    """One plain line for a task event, e.g. 'read_file core/x.py -> succeeded' or 'run_tests -> PASS'."""
    try:
        d = json.loads(payload) if isinstance(payload, str) else dict(payload or {})
    except ValueError:
        d = {}
    if kind == 'test_result':
        return 'run_tests -> ' + ('PASS' if d.get('alm_run_status') == 'pass' else str(d.get('alm_run_status') or d.get('status') or 'done').upper())
    tool = str(d.get('tool') or kind)
    args = d.get('arguments') if isinstance(d.get('arguments'), dict) else {}
    what = str(args.get('path') or args.get('query') or args.get('action') or args.get('step_id') or '')[:80]
    result = 'failed: ' + str(d.get('error') or '')[:100] if kind == 'tool_failure' else str(d.get('status') or 'done')
    return f'{tool}{" " + what if what else ""} -> {result}'


def snapshot(conn, now=None, background=None, limit=6):
    now = time.time() if now is None else now
    tables = _tables(conn)
    lines = []
    if {'hb_executions', 'hb_tasks'} <= tables:
        for task_id, request_id, agent, started, title in conn.execute(
                "SELECT e.task_id, e.request_id, e.agent, e.started_at, t.title FROM hb_executions e JOIN hb_tasks t ON t.task_id=e.task_id "
                "WHERE e.state='running' ORDER BY e.started_at").fetchall():
            stage = conn.execute('SELECT stage FROM hb_peer_work WHERE request_id=?', (request_id,)).fetchone() if 'hb_peer_work' in tables else None
            lines.append(f"{str(agent).upper()} ({WHERE.get(agent, 'model')}) - {str(title)[:90]} - running {_took(now - (started or now))}")
            lines.append('  stage: ' + (str(stage[0])[:120] if stage and stage[0] else 'working'))
            if 'hb_task_events' in tables:
                events = conn.execute(f"SELECT kind, payload FROM hb_task_events WHERE task_id=? AND request_id=? AND kind IN ({','.join('?' * len(KINDS))}) "
                                      "ORDER BY event_id DESC LIMIT ?", (task_id, request_id, *KINDS, limit)).fetchall()
                lines += ['  ' + event_line(k, p) for k, p in reversed(events)]
    if background is None:
        try:
            from core import hb_background
            background = hb_background.snapshot()
        except Exception:
            background = []
    for job in background:
        steps = job.get('steps') or []
        lines.append(f"{str(job.get('role', 'background')).upper()} ({job.get('model', '?')}, CPU / RAM) - {str(job.get('task', ''))[:90]}"
                     + (f" - {steps[-1].get('what', '')}"[:140] if steps else ''))
    return {'running': bool(lines), 'lines': lines}
