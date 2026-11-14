"""HB's clipboard (owner 14 Nov 2026): one task list that HB controls; APEX ticks tasks off; finished ones drop into Studio/KC.

"It is dynamic and it can be edited by me or APEX or HB or you. Whenever a new task gets added it is measured for importance and
dependencies on other tasks and the list is reshuffled and prioritised, as well as who the owner/doer is, so HB can line up the
models per task."

  rows(conn)      the list as the holder shows it: order, title, state, doer and why, importance, Ready (homework card), check result
  order_key(...)  the order HB works in: pinned first, then importance (5 high), then plan order; used by the plan workflow
  edit(...)       /clip up|down|top S-xxxx · /clip importance S-xxxx 1-5 · /clip doer S-xxxx hb|small|apex|fred · /clip clear S-xxxx
                  Every edit is recorded with who made it (JD, APEX, HB, Claude Code).

Importance and doer come from the homework spec card (core/hb_homework.py) unless someone set them by hand; by hand always wins.
Dependencies stay where they are recorded (Studio step deps, "HB depends on:" lines); a task never starts before them.
Finished tasks leave the list: their record lives in Studio and the Knowledge Centre.
"""
import time

from core import hb_tasks

DOERS = ('hb', 'small', 'apex', 'fred')
DOER_WORDS = {'hb': 'HB itself (no model)', 'small': 'small CPU model', 'apex': 'APEX (14B on the GPU)', 'fred': 'Fred (24B on the CPU)'}


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_clipboard(step_id TEXT PRIMARY KEY, importance INTEGER, doer TEXT, pin REAL,
        edited_by TEXT, updated_at REAL)''')


def _override(conn, step_id):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hb_clipboard'").fetchone():
        return {}
    row = conn.execute('SELECT importance, doer, pin, edited_by FROM hb_clipboard WHERE step_id=?', (step_id,)).fetchone()
    return dict(zip(('importance', 'doer', 'pin', 'edited_by'), row)) if row else {}


def _card(conn, task_id):
    if not task_id:
        return None
    from core.hb_homework import latest
    task = hb_tasks.get(conn, task_id)
    return latest(conn, task) if task else None


def facts(conn, step):
    """importance, doer, why, ready for one queue step (by hand > homework card > default)."""
    o = _override(conn, step['step_id'])
    card = _card(conn, step.get('task_id')) or {}
    importance = o.get('importance') or card.get('importance') or 3
    doer = o.get('doer') or card.get('doer') or 'apex'
    why = (f"set by {o['edited_by']}" if o.get('doer') or o.get('importance') else card.get('why') or 'default: APEX does code work')
    return {'importance': int(importance), 'doer': doer, 'doer_words': DOER_WORDS.get(doer, doer), 'why': str(why)[:200],
            'ready': bool(card.get('ready')), 'check': card.get('check') or '', 'pin': o.get('pin')}


def order_key(conn, step, position):
    f = facts(conn, step)
    return (0 if f['pin'] is not None else 1, f['pin'] if f['pin'] is not None else 0, -f['importance'], position)


def ordered(conn, steps):
    return [s for _, s in sorted(((order_key(conn, s, n), s) for n, s in enumerate(steps)), key=lambda x: x[0])]


def _last_check(conn, task_id):
    row = conn.execute("SELECT json_extract(payload,'$.alm_run_status') FROM hb_task_events WHERE task_id=? AND kind='test_result' "
                       "ORDER BY event_id DESC LIMIT 1", (task_id,)).fetchone() if task_id else None
    return {'pass': 'passing', 'fail': 'failing'}.get(row[0] if row else None, 'not run yet')


def rows(conn):
    from core import hb_queue
    out = []
    for item in hb_queue.items(conn):
        f = facts(conn, {'step_id': item['step_id'], 'task_id': item['task_id']})
        out.append({**item, **f, 'check_result': _last_check(conn, item['task_id'])})
    return out


def edit(conn, args, actor):
    """/clip up|down|top S-xxxx · /clip importance S-xxxx 1-5 · /clip doer S-xxxx hb|small|apex|fred · /clip clear S-xxxx"""
    import re
    ensure_schema(conn)
    if len(args) < 2 or not re.fullmatch(r'S-[0-9A-F]{10}', args[1].upper()):
        return 'Use /clip up|down|top|clear S-xxxx, /clip importance S-xxxx 1-5, or /clip doer S-xxxx hb|small|apex|fred.'
    action, step_id = args[0].lower(), args[1].upper()
    if not conn.execute('SELECT 1 FROM project_steps WHERE step_id=?', (step_id,)).fetchone():
        return f'{step_id} is not a Studio step.'
    conn.execute('INSERT OR IGNORE INTO hb_clipboard(step_id, edited_by, updated_at) VALUES(?,?,?)', (step_id, actor, time.time()))
    if action == 'importance' and len(args) > 2 and args[2] in '12345' and len(args[2]) == 1:
        conn.execute('UPDATE hb_clipboard SET importance=?, edited_by=?, updated_at=? WHERE step_id=?', (int(args[2]), actor, time.time(), step_id))
        said = f'importance {args[2]}'
    elif action == 'doer' and len(args) > 2 and args[2].lower() in DOERS:
        conn.execute('UPDATE hb_clipboard SET doer=?, edited_by=?, updated_at=? WHERE step_id=?', (args[2].lower(), actor, time.time(), step_id))
        said = f'doer: {DOER_WORDS[args[2].lower()]}'
    elif action in ('up', 'down', 'top'):
        pins = [r[0] for r in conn.execute('SELECT pin FROM hb_clipboard WHERE pin IS NOT NULL AND step_id<>?', (step_id,))]
        mine = _override(conn, step_id).get('pin')
        pin = (min(pins, default=1) - 1 if action == 'top' else (mine if mine is not None else max(pins, default=0)) + (-1.5 if action == 'up' else 1.5))
        conn.execute('UPDATE hb_clipboard SET pin=?, edited_by=?, updated_at=? WHERE step_id=?', (pin, actor, time.time(), step_id))
        said = {'top': 'moved to the top', 'up': 'moved up', 'down': 'moved down'}[action]
    elif action == 'clear':
        conn.execute('DELETE FROM hb_clipboard WHERE step_id=?', (step_id,))
        said = 'back to HB\'s own order, importance and doer'
    else:
        return 'Use /clip up|down|top|clear S-xxxx, /clip importance S-xxxx 1-5, or /clip doer S-xxxx hb|small|apex|fred.'
    task = conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? AND state NOT IN ('completed','cancelled') ORDER BY created_at DESC LIMIT 1",
                        (step_id,)).fetchone()
    if task:
        hb_tasks.event(conn, hb_tasks.get(conn, task[0]), 'hummingbird', 'clipboard_edit', {'action': action, 'args': args[2:], 'actor': actor})
    return f'Clipboard: {step_id} {said} ({actor}). Dependencies still decide what can start.'
