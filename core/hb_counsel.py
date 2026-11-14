"""HB counsel (owner 14 Nov 2026): HB looks into the vague steps itself and proposes options for JD to review.

"I expect the homework / nanny counsel should look at what is in the system already, tell us why it's not working and then propose
solutions so we can review."

For each vague step in the queue (marked "needs a spec", or a short description with no done criteria), one at a time in the background:
  1 facts   HB's own tools: the code lines and files the step's words point to (hb_homework.facts) and the KC documents about it
  2 review  the counsel model (Fred, the larger CPU model) writes JSON: what already exists, why it is not working, 2-3 options (how,
            effort S/M/L, risk), the recommended option and a concrete first step with its check
  3 post    main chat shows it; JD picks with /pick S-xxxx N - the chosen option becomes the step's spec ("Done when" from its check)
Never while Fred is taking over a stuck step; nothing in HB changes until JD picks.
"""
import json
import re
import threading
import time
from contextlib import closing

from core import hb_tasks

PLAN = 'P-2AB8250A87'
MAIN_CHAT = 2834
MODEL = 'fred-cpu:24b'          # the counsel role; moves to role assignment with the "roles, not names" work (S-9F36B5AB4E)
RECHECK_DAYS = 7
_RUNNING = threading.Lock()
SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['exists', 'why_not_working', 'options', 'recommended', 'first_step', 'check'],
          'properties': {'exists': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string', 'maxLength': 200}},
                         'why_not_working': {'type': 'string', 'maxLength': 600},
                         'options': {'type': 'array', 'minItems': 2, 'maxItems': 3, 'items': {'type': 'object', 'additionalProperties': False,
                                     'required': ['title', 'how', 'effort', 'risk'],
                                     'properties': {'title': {'type': 'string', 'maxLength': 120}, 'how': {'type': 'string', 'maxLength': 500},
                                                    'effort': {'type': 'string', 'enum': ['S', 'M', 'L']}, 'risk': {'type': 'string', 'maxLength': 200}}}},
                         'recommended': {'type': 'integer', 'minimum': 1, 'maximum': 3},
                         'first_step': {'type': 'string', 'maxLength': 400}, 'check': {'type': 'string', 'maxLength': 300}}}


def _latest(conn, task_id):
    row = conn.execute("SELECT payload, created_at FROM hb_task_events WHERE task_id=? AND kind='counsel' ORDER BY event_id DESC LIMIT 1",
                       (task_id,)).fetchone()
    return (json.loads(row[0]), row[1]) if row else (None, None)


def vague(conn, step):
    """Why this queue step needs counsel, or None."""
    if str(step.get('skip') or '').startswith('needs a spec'):
        return step['skip']
    # Owner 14 Nov: a step marked "HB needs a spec" is counsel work even when it is held or parked (that is why it stopped).
    from core.hb_plan_workflow import SPEC_MARK
    desc = conn.execute('SELECT description FROM project_steps WHERE step_id=?', (step['step_id'],)).fetchone()
    if step.get('task_id') and desc and SPEC_MARK in str(desc[0] or '') and not str(step.get('skip') or '').startswith(('blocked', 'not APEX')):
        return 'not scoped in Studio yet'
    if step.get('skip') or not step.get('task_id'):
        return None
    from core.hb_dream_method import done_when
    task = hb_tasks.get(conn, step['task_id'])
    desc = conn.execute('SELECT description FROM project_steps WHERE step_id=?', (step['step_id'],)).fetchone()
    if task and not done_when(conn, task)[1] and len(str(desc[0] if desc else '')) < 400:
        return 'short description and no done criteria'
    return None


def candidates(conn, now=None):
    from core import hb_plan_workflow as wf
    now = time.time() if now is None else now
    out = []
    for s in wf.steps(conn):
        why = vague(conn, s) if s.get('task_id') else None
        if not why:
            continue
        _, at = _latest(conn, s['task_id'])
        if at and now - at < RECHECK_DAYS * 86400:
            continue
        out.append((s, why))
    return out


def gather(conn, task):
    from core.hb_homework import facts
    found = facts(conn, task)
    kc = []
    try:
        from core.apex_knowledge import search
        words = ' '.join(re.findall(r'[A-Za-z][A-Za-z0-9_-]{3,}', str(task.get('title') or ''))[:6])
        res = search(words) if words else {}
        kc = [{'title': i.get('title'), 'excerpt': str(i.get('excerpt') or '')[:300]} for i in (res.get('items') or [])[:4]]
    except Exception:
        pass
    return {'code': found['files'], 'kc': kc, 'done_when': found['done_when'], 'studio': studio_history(conn, task)}


def studio_history(conn, task, limit=8):
    """Owner 14 Nov: the work behind these steps exists - it was never scoped or recorded properly. Earlier Studio steps in ANY project
    (archived and done ones too) whose title shares two or more significant words with this step."""
    from core.hb_dream_method import _words
    mine = _words(task.get('title') or '')
    out = []
    for sid, project, title, status, desc in conn.execute(
            "SELECT step_id, project_id, title, status, description FROM project_steps WHERE step_id<>?", (task.get('step_id') or '',)):
        shared = mine & _words(title)
        if len(shared) >= 2:
            out.append({'step_id': sid, 'project_id': project, 'title': str(title)[:120], 'status': status,
                        'about': str(desc or '')[:240], 'shared': len(shared)})
    return sorted(out, key=lambda r: -r['shared'])[:limit]


def call_model(messages):
    from core import llm
    text, _ = llm.chat_via_gateway(MODEL, messages, temperature=0.2, absolute_timeout_s=1200, idle_timeout_s=400, queue_timeout_s=10,
                                   keep_alive=600, options={'num_ctx': 16384, 'num_predict': 1200, 'timeout': 1200, 'startup_timeout': 300,
                                                            'require_complete_output': True},
                                   response_format={'type': 'json_schema', 'json_schema': {'name': 'hb_counsel', 'strict': True, 'schema': SCHEMA}})
    return json.loads(text)


def prompt(task, facts, why):
    from core.hb_master_prompt import for_role
    system = (for_role('fred') + '\nYou are HB\'s counsel. This step in JD\'s plan is not new: a lot of the work behind it already exists '
              'but was never scoped or recorded properly in Studio. Using ONLY the facts below (code lines, Knowledge Centre documents and '
              'earlier Studio steps in any project, done and archived ones too), say what already exists and is done, what is left, why it is '
              'not finished, and 2-3 options to finish what is left (how, effort S/M/L, risk). Recommend one, and give its first concrete step with a check that proves it '
              '(a test, a command or an exact visible behaviour). Never invent files or features that the facts do not show; say when '
              'the facts are thin. Plain words. Answer JSON only.')
    user = json.dumps({'step': str(task.get('title') or '')[:200], 'description': str(task.get('objective') or '')[:1500], 'why_vague': why,
                       'facts': facts})
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def review(conn, task, why, model=call_model):
    from core import hb_background as bg
    bg.start('counsel', task, MODEL, f"looking into {str(task.get('title') or '')[:70]}: what exists, what is left", conn)
    try:
        return _review(conn, task, why, model, bg)
    finally:
        bg.finish('counsel')


def _review(conn, task, why, model, bg):
    facts = gather(conn, task)
    bg.step('counsel', f"found {len(facts['code'])} code file(s), {len(facts['kc'])} KC document(s), {len(facts.get('studio') or [])} earlier Studio step(s); asking {MODEL}")
    card = model(prompt(task, facts, why))
    card['options'] = card.get('options', [])[:3]
    card['recommended'] = max(1, min(int(card.get('recommended') or 1), len(card['options']) or 1))
    hb_tasks.event(conn, task, 'hummingbird', 'counsel', {**card, 'why_vague': why, 'model': MODEL, 'facts_files': [f['path'] for f in facts['code']]})
    from core.hb_plain import message, name
    lines = [f"{n}. {o['title']} ({o['effort']}) - {o['how']}" + (f" Risk: {o['risk']}" if o.get('risk') else '') for n, o in enumerate(card['options'], 1)]
    text = message(f"🔎 HB looked into {name(task.get('title'))}: {card.get('why_not_working', '')[:300]}",
                   *lines, f"HB recommends option {card['recommended']}. First step: {card.get('first_step', '')} (check: {card.get('check', '')})",
                   f"Pick with /pick {task['step_id']} N",
                   details=['already there: ' + '; '.join(card.get('exists') or ['nothing found']), f'why HB looked: {why}'])
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                       (task['conversation_id'], text)).lastrowid    # the task's own chat, not a fixed number
    hb_tasks.bind(conn, task['conversation_id'], mid, task_id=task['task_id'], kind='reply')
    return card


def pick(conn, step_id, number, actor):
    """/pick S-xxxx N: JD's choice becomes the step's spec (Done when = the option's check). Returns HB's answer."""
    row = conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? AND state NOT IN ('completed','cancelled') ORDER BY created_at DESC LIMIT 1",
                       (step_id,)).fetchone()
    if not row:
        return f'{step_id} has no open task.'
    task = hb_tasks.get(conn, row[0])
    card, _ = _latest(conn, task['task_id'])
    if not card:
        return f'HB has not looked into {step_id} yet.'
    if not 1 <= number <= len(card['options']):
        return f"Pick 1-{len(card['options'])}."
    o = card['options'][number - 1]
    check = card['check'] if number == card['recommended'] else f"{o['title']} works: {card['check']}"
    spec = (f"\nSPEC (JD picked option {number} on {time.strftime('%d %b')}): {o['title']} - {o['how']}\nFirst step: "
            f"{card['first_step'] if number == card['recommended'] else o['how']}\nDone when: {check}\n")
    from core.hb_plan_workflow import SPEC_MARK      # 14 Nov fix: the pick IS the spec, so the "needs a spec" mark goes (else the step stays vague)
    conn.execute('UPDATE project_steps SET description=replace(description, ?, ?)||?, updated_at=? WHERE step_id=?',
                 (SPEC_MARK, 'Scoped by HB counsel, picked by JD:', spec, time.time(), step_id))
    conn.execute('UPDATE hb_tasks SET objective=objective||?, updated_at=? WHERE task_id=?', (spec, time.time(), task['task_id']))
    hb_tasks.event(conn, task, 'user', 'counsel_pick', {'option': number, 'actor': actor, 'title': o['title']})
    return f"{step_id}: option {number} ({o['title']}) is now its spec. HB writes its homework card next and it joins the queue."


def can_run(conn):
    try:   # owner 14 Nov: the model benchmark has the CPU while it runs
        from core.hb_model_bench import running as bench_running
        if bench_running():
            return False
    except Exception:
        pass
    return _can_run(conn)


def _can_run(conn):
    if conn.execute("SELECT name FROM sqlite_master WHERE name='hb_peer_work'").fetchone() and conn.execute(
            "SELECT 1 FROM hb_task_events e JOIN hb_peer_work w ON w.request_id=e.request_id WHERE e.kind='fred_turn' AND w.state IN ('queued','running')").fetchone():
        return False
    # Owner 14 Nov: "let the current tasks finish, then propose the specs" - only while the queue has no precise work running or ready.
    try:
        from core import hb_plan_workflow as wf
        w = wf.settings(conn) or {}
        if w.get('enabled') and (w.get('task_id') or wf.next_ready(conn)):
            return False
    except Exception:
        pass
    from core.hb_model_switches import current_modes
    return current_modes().get(MODEL) != 'off'


def tick(conn):
    if not _RUNNING.acquire(blocking=False):
        return None
    try:
        todo = candidates(conn) if can_run(conn) else []
    except Exception:
        _RUNNING.release()
        raise
    if not todo:
        _RUNNING.release()
        return None
    step, why = todo[0]

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own, own:
                review(own, hb_tasks.get(own, step['task_id']), why)
        except Exception:
            import logging
            logging.getLogger('hb.counsel').exception('counsel failed for %s', step['step_id'])
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-counsel', daemon=True).start()
    return step['step_id']
