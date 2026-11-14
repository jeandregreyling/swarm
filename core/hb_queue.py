"""HB drives the open tasks to the finish (owner 14 Nov 2026).

"Those tasks should show in a little holder with HB in the chat window and HB should drive the system and APEX to complete them
until they are completed and successful."

The driver is the plan workflow of the living plan (core/hb_plan_workflow) with auto-approve on: one step at a time, in plan
order, APEX scopes it, HB approves the plan itself, the task manager runs APEX turns, Fred helps when APEX is stuck, and HB
approves the step when its own checks pass. HB stops for JD only on real problems (loops, repeated failures Fred could not fix).

  drive_on(conn, actor, ...)   JD said go ("GO", "keep going", "work on the open tasks", /drive): workflow + auto-approve on,
                               and the tasks JD's last Stop held are released back into the queue (they wait their turn).
  items(conn)                  what the holder in main chat shows: now / next / waiting / needs JD, plus done counts.
  summary(conn, ...)           one line for APEX's chat replies and for /drive status.
"""
import time

from core import hb_tasks
from core import hb_plan_workflow as wf

PROJECT = wf.DEFAULT_PROJECT
MAIN_CHAT = wf.MAIN_CHAT


def _plain(title):
    try:
        from core.hb_plain import name
        return name(title)
    except Exception:
        return str(title or '')[:80]


def items(conn, project_id=PROJECT):
    """[{step_id, task_id, title, state, why}] in plan order. state: now | next | waiting | needs_you | not_apex | blocked."""
    w = wf.settings(conn, project_id) or {}
    out = []
    first_ready = True
    for s in wf.steps(conn, project_id):
        skip = s['skip'] or ''
        if s['step_id'] == w.get('step_id') and w.get('enabled'):
            manager = conn.execute('SELECT state, detail FROM hb_task_manager WHERE task_id=?', (s['task_id'],)).fetchone() \
                if s['task_id'] else None
            state = 'needs_you' if manager and manager[0] == 'needs_owner' else 'now'
            why = (manager[1] if manager else '') or w.get('stage') or ''
        elif skip.startswith('not APEX work'):
            continue                                     # Claude Code's / HB's own register steps are not in APEX's queue
        elif skip.startswith('blocked'):
            state, why = 'blocked', skip
        elif skip == 'waiting for your approval':
            state, why = 'needs_you', skip
        elif not skip and first_ready:
            state, why, first_ready = 'next', '', False
        else:
            state, why = 'waiting', skip
        out.append({'step_id': s['step_id'], 'task_id': s['task_id'], 'title': _plain(s['title']), 'state': state,
                    'why': str(why)[:160]})
    return out


def counts(conn, project_id=PROJECT, since=None):
    since = since if since is not None else time.time() - 86400
    done = conn.execute("SELECT COUNT(*) FROM project_steps WHERE project_id=? AND status='done' AND updated_at>=?",
                        (project_id, since)).fetchone()[0] if wf._has(conn, 'project_steps') else 0
    return {'done_24h': done}


def status(conn, conversation_id=MAIN_CHAT, project_id=PROJECT):
    w = wf.settings(conn, project_id) or {}
    rows = items(conn, project_id)
    try:   # owner 14 Nov: clipboard columns (doer, importance, Ready, check result) in clipboard order
        from core import hb_clipboard
        extra = {r['step_id']: r for r in hb_clipboard.rows(conn)}
        rows = [{**r, **{k: extra[r['step_id']][k] for k in ('importance', 'doer', 'doer_words', 'why', 'ready', 'check', 'check_result')}}
                if r['step_id'] in extra else r for r in rows]
        head = [r for r in rows if r['state'] in ('now', 'needs_you')]
        rest = hb_clipboard.ordered(conn, [r for r in rows if r['state'] not in ('now', 'needs_you', 'blocked')])
        rows = head + rest + [r for r in rows if r['state'] == 'blocked']
    except Exception:
        pass
    from core import hb_background
    background = [{'role': j['role'], 'model': j['model'], 'task': j['task'], 'now': j['steps'][-1]['what']} for j in hb_background.snapshot()]
    return {'on': bool(w.get('enabled')), 'auto': bool(w.get('auto_accept')), 'background': background, 'stage': w.get('stage') or 'idle',
            'note': w.get('note') or '', 'items': rows, 'open': len([r for r in rows if r['state'] != 'blocked']),
            **counts(conn, project_id)}


def summary(conn, conversation_id=MAIN_CHAT, project_id=PROJECT):
    s = status(conn, conversation_id, project_id)
    now = [r for r in s['items'] if r['state'] in ('now', 'needs_you')]
    nxt = [r for r in s['items'] if r['state'] == 'next']
    head = 'HB is driving the queue' if s['on'] else 'The queue driver is off (JD starts it with "go" or /drive)'
    parts = [f"{head}; {s['open']} open, {s['done_24h']} finished in the last 24 h"]
    if now:
        live = conn.execute("SELECT state FROM hb_task_manager WHERE task_id=? AND enabled=1", (now[0]['task_id'],)).fetchone() \
            if now[0].get('task_id') and wf._has(conn, 'hb_task_manager') else None
        doing = ('needs JD' if now[0]['state'] == 'needs_you' else 'APEX turn running' if live and live[0] == 'running'
                 else 'queued for APEX' if live else 'NOT running yet - say so, do not claim you are doing it')
        parts.append(f"now: {now[0]['title']} ({now[0]['step_id']}, {doing})")
    if nxt:
        parts.append(f"next: {nxt[0]['title']} ({nxt[0]['step_id']})")
    return '; '.join(parts) + '.'


def release_held(conn, actor, owner_message_id=None, project_id=PROJECT):
    """Tasks JD's Stop held go back into the queue. They do not all start: the workflow takes them one at a time."""
    released = []
    for s in wf.steps(conn, project_id):
        if not s['task_id'] or not str(s['skip'] or '').startswith('held by you') or not global_hold(_owner_choice(conn, s['task_id'])):
            continue                                     # JD's own Off on a task wins over global Auto
        task = hb_tasks.get(conn, s['task_id'])
        conn.execute("UPDATE hb_tasks SET state='active', updated_at=? WHERE task_id=? AND state='paused'", (time.time(), task['task_id']))
        current = (wf.settings(conn, project_id) or {}).get('task_id') == task['task_id']
        if wf._has(conn, 'hb_task_manager') and not current:   # the step the workflow runs stays with the task manager
            conn.execute("UPDATE hb_task_manager SET enabled=0, state='queued', detail=?, updated_at=? WHERE task_id=?",
                         ("Waiting its turn in HB's queue", time.time(), task['task_id']))
        elif wf._has(conn, 'hb_task_manager'):                 # JD's go = back to work, with a fresh try after a stall
            conn.execute("UPDATE hb_task_manager SET enabled=1, state='queued', next_due=?, recovery_count=0, "
                         "phase=CASE WHEN phase='review' THEN 'execute' ELSE phase END, detail=?, updated_at=? WHERE task_id=?",
                         (time.time(), "JD's go-ahead: back to work", time.time(), task['task_id']))
        hb_tasks.event(conn, task, 'user', 'continuation_control',
                       {'mode': 'auto', 'via': 'drive', 'actor': actor, 'owner_message_id': owner_message_id,
                        'source': "JD's go-ahead released the Stop hold; HB's queue runs it in its turn"})
        released.append(task['task_id'])
    # Tasks outside the plan that Auto off held go back to Auto too, and run on their own (not in the plan queue).
    for (tid,) in conn.execute("SELECT task_id FROM hb_tasks WHERE state='paused'").fetchall():
        if tid in released or not global_hold(_owner_choice(conn, tid)):
            continue
        task = hb_tasks.get(conn, tid)
        if task.get('project_id') == project_id:
            continue                                     # plan tasks were handled above
        conn.execute("UPDATE hb_tasks SET state='active', updated_at=? WHERE task_id=?", (time.time(), tid))
        hb_tasks.event(conn, task, 'user', 'continuation_control',
                       {'mode': 'auto', 'via': 'drive', 'actor': actor, 'owner_message_id': owner_message_id,
                        'source': 'Auto switched on: every task back to Auto'})
        released.append(tid)
    return released


def drive_on(conn, actor, conversation_id=None, owner_message_id=None, project_id=PROJECT):
    """JD said go. Returns the plain text HB posts."""
    conversation_id = conversation_id or (wf.settings(conn, project_id) or {}).get('conversation_id') or MAIN_CHAT
    first = not (wf.settings(conn, project_id) or {}).get('decided_at')
    wf.configure(conn, True, actor, project_id, conversation_id)
    if first:                                            # Approve defaults to on; after that JD's Approve choice is remembered
        wf.set_auto_accept(conn, True, actor, project_id)
    released = release_held(conn, actor, owner_message_id, project_id)
    w = wf.settings(conn, project_id)
    if not w['task_id']:
        wf._update(conn, project_id, stage='idle')
    wf.tick(conn)
    from core.hb_plain import message
    approving = bool((wf.settings(conn, project_id) or {}).get('auto_accept'))
    return message('▶ HB is driving the open tasks.',
                   summary(conn, conversation_id, project_id),
                   'HB approves each plan and each finished step itself when its checks pass, and only stops for you on real problems.'
                   if approving else 'Approve is off: plans and finished steps wait for your approval.',
                   details=[f'released from your Stop: {", ".join(released)}' if released else 'nothing was held',
                            '"stop" or "cancel all tasks" stops it; /drive status shows it'])


def global_on(conn, project_id=PROJECT):
    """The global Auto switch. True while HB drives the queue; also True when no global switch was ever set (older stores)."""
    w = wf.settings(conn, project_id) if wf._has(conn, 'hb_plan_workflow') else None
    return True if w is None else bool(w['enabled'])


def global_hold(choice):
    """A hold made by a global Off (the Auto switch, "stop", "cancel all tasks") - released by global Auto. A task JD switched Off
    by itself is not a global hold: it stays off until JD switches it On or Auto."""
    return choice.get('mode') == 'off' and (choice.get('via') == 'global' or str(choice.get('command_id') or '').startswith('owner-chat-stop-'))


def _owner_choice(conn, task_id):
    import json
    row = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='continuation_control' AND agent='user' "
                       "ORDER BY event_id DESC LIMIT 1", (task_id,)).fetchone()
    try:
        return json.loads(row[0]) if row else {}
    except (TypeError, ValueError):
        return {}


def drive_off(conn, actor, conversation_id=None, project_id=PROJECT):
    """Owner 14 Nov: "the global switches set everything to off or auto". Auto off holds every open task of the chat, also one JD
    had switched On by itself; a task JD switches On after this runs on its own (an individual override) until the next global flip."""
    from core.hb_owner_intent import is_chat_task
    conversation_id = conversation_id or (wf.settings(conn, project_id) or {}).get('conversation_id') or MAIN_CHAT
    wf.configure(conn, False, actor, project_id, conversation_id)
    held = []
    for (tid,) in conn.execute("SELECT task_id FROM hb_tasks WHERE conversation_id=? AND state NOT IN ('completed','cancelled','paused')",
                               (conversation_id,)).fetchall():
        task = hb_tasks.get(conn, tid)
        choice = _owner_choice(conn, tid)
        managed = wf._has(conn, 'hb_task_manager') and conn.execute(
            'SELECT 1 FROM hb_task_manager WHERE task_id=? AND enabled=1', (tid,)).fetchone()
        if is_chat_task(task) or not (managed or choice.get('mode') in ('on', 'auto')):
            continue
        conn.execute("UPDATE hb_tasks SET state='paused', updated_at=? WHERE task_id=?", (time.time(), tid))
        hb_tasks.event(conn, task, 'user', 'continuation_control',
                       {'mode': 'off', 'via': 'global', 'actor': actor, 'source': 'Auto switched off: every task is off'})
        held.append(tid)
    return ('Auto is off: HB stopped driving and every task is held' + (f' ({len(held)})' if held else '') +
            ' with its record intact. A task you switch On runs by itself; Auto or "go" starts everything again.')


def command(conn, conversation_id, args, actor):
    sub = (args[0] if args else 'on').lower()
    if sub in ('off', 'stop'):
        return drive_off(conn, actor, conversation_id)
    if sub == 'status':
        return summary(conn, conversation_id)
    return drive_on(conn, actor, conversation_id)


def set_switch(conn, which, on, actor):
    """The two main-chat switches (owner 14 Nov): Auto = HB drives the queue; Approve = HB approves plans and finished steps
    itself. Approve only works while Auto is on, so the page shows it only then; its setting is remembered across Auto off/on."""
    if which == 'auto':
        return drive_on(conn, actor) if on else drive_off(conn, actor)
    if which == 'approve':
        if not (wf.settings(conn) or {}).get('enabled'):
            raise ValueError('Approve only works while Auto is on')
        return wf.set_auto_accept(conn, bool(on), actor)
    raise ValueError('switch must be auto or approve')
