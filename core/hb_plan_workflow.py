"""HB runs a Studio plan as a workflow (owner 12 Nov: "I approved all of them but the workflows haven't actually kicked off").

One plan step at a time, in plan order, the DREAM way, with HB holding the clipboard:
  1 Distinguish  APEX scopes the next ready step with read-only tools and proposes "Done when" + a short plan.
  2 Owner        approves the plan in the Needs-you bar (/plan T-...), writes their own (/done T-...) or skips it (/cancel T-...).
  3 Execute      HB's task manager runs APEX turns under the stop rules and the review gate.
  4 Owner        approves the finished step (Approve, /accept S-...). HB then starts the next ready step.

The workflow is off until the owner starts it (/workflow on, or Start in the bar); /workflow off and /stop stop it.
While it is on, the step it is running counts as the owner's go-ahead for that task (see grant()); an explicit
Continue On/Off on a task always wins, and a task the owner holds is skipped, never forced.
"""
import json
import re
import sqlite3
import time

from core import hb_tasks

DEFAULT_PROJECT = 'P-2AB8250A87'          # the single living plan
MAIN_CHAT = 2834
FINISHED_RECHECK_S = 60
PLAN_TOOLS = ['task_context', 'task_evidence', 'read_file', 'grep_repo', 'git_status', 'alm_step_get', 'memory_search',
              'knowledge_search', 'knowledge_read', 'runtime_status', 'backlog_list', 'reference_lookup']
PLAN_INSTRUCTION = (
    'HB workflow, DREAM step 1 (Distinguish): scope this Studio step before any work is done. Use read-only tools '
    '(task_context, knowledge_search / knowledge_read, memory_search, read_file, grep_repo, runtime_status) to find what already '
    'exists. Nothing may be changed in this turn. Then reply in plain text with exactly these three sections:\n'
    'Found: 2-5 lines on what already exists, citing files or KC documents.\n'
    'Done when: 2-5 lines, one checkable condition per line (a test that passes, a command result, a visible behaviour in HB).\n'
    'Plan: 3-7 numbered small steps; step 1 must be doable in one turn.\n'
    'The owner approves the plan before HB runs it.')
_SECTION = re.compile(r'^\s*[#>*_\s]*(found|done when|definition of done|acceptance criteria|plan)\s*[*_]*\s*[:\-]\s*[*_]*\s*(.*)$', re.I)
_BULLET = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s*')


def _has(conn, table):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_plan_workflow(
        project_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, conversation_id INTEGER, actor TEXT, decided_at REAL,
        task_id TEXT, step_id TEXT, stage TEXT NOT NULL DEFAULT 'idle', request_id INTEGER, preferred_step TEXT,
        note TEXT NOT NULL DEFAULT '', updated_at REAL)''')
    if 'auto_accept' not in {r[1] for r in conn.execute('PRAGMA table_info(hb_plan_workflow)')}:
        conn.execute('ALTER TABLE hb_plan_workflow ADD COLUMN auto_accept INTEGER NOT NULL DEFAULT 0')


def settings(conn, project_id=DEFAULT_PROJECT):
    """The saved workflow of a plan, or None when the owner never decided."""
    if not _has(conn, 'hb_plan_workflow'):
        return None
    cur = conn.execute('SELECT * FROM hb_plan_workflow WHERE project_id=?', (project_id,))
    row = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], tuple(row))) if row else None


def _update(conn, project_id, **values):
    values['updated_at'] = time.time()
    conn.execute(f"UPDATE hb_plan_workflow SET {', '.join(k + '=?' for k in values)} WHERE project_id=?", (*values.values(), project_id))


def auto_accept_for(conn, task):
    """Owner 13 Nov: approvals are automatic while the workflow runs. True when the enabled workflow is running this task with
    auto-accept on. HB then approves a step whose own checks pass after its last change; real problems still stop for the owner."""
    if not _has(conn, 'hb_plan_workflow') or not task or not task.get('step_id'):
        return False
    ensure_schema(conn)
    row = conn.execute('SELECT 1 FROM hb_plan_workflow WHERE enabled=1 AND auto_accept=1 AND task_id=?', (task['task_id'],)).fetchone()
    return bool(row)


def set_auto_accept(conn, on, actor, project_id=DEFAULT_PROJECT):
    ensure_schema(conn)
    if not settings(conn, project_id):
        configure(conn, False, actor, project_id)
    _update(conn, project_id, auto_accept=int(bool(on)), note=('Auto-approve on' if on else 'Auto-approve off') + f' ({actor})')
    return ('Auto-approve ON: while the workflow runs, HB approves a step itself when its own checks pass after its last change, '
            'records it in the chat, and moves on. It still stops for you on loops, stalls Fred could not fix, and repeated failures.'
            if on else 'Auto-approve off: finished steps wait for your Approve.')


def grant(conn, task):
    """The owner's standing go-ahead for this task: its plan's workflow is on and this is the step it is running.
    Used by hb_chat_controls.continuation() only when the owner never set Continue on the task itself."""
    try:
        row = conn.execute('SELECT actor, decided_at, project_id FROM hb_plan_workflow WHERE enabled=1 AND task_id=?',
                           (task['task_id'],)).fetchone()
    except sqlite3.OperationalError:
        return None
    return {'actor': row[0] or 'owner', 'since': row[1], 'project_id': row[2]} if row else None


def _owner_mode(conn, task_id):
    """The owner's own Continue choice on a task ('on'/'off'/'auto'), or None when they never set one."""
    row = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='continuation_control' AND agent='user' "
                       "ORDER BY event_id DESC LIMIT 1", (task_id,)).fetchone()
    try:
        saved = json.loads(row[0]) if row else {}
    except (TypeError, ValueError):
        return None
    # Owner 14 Nov: JD's "go" (core/hb_queue) releases a Stop hold back into the queue; that is not a Continue choice of its own.
    # Owner 14 Nov: per-task Auto follows the global switch, so a plan task on Auto simply takes its turn in the queue.
    return None if saved.get('via') == 'drive' or saved.get('mode') == 'auto' else saved.get('mode')


def steps(conn, project_id=DEFAULT_PROJECT):
    """Every open step of the plan in order, with its HB task and why the workflow would skip it (None = ready)."""
    from core.hb_commands import ACCEPTANCE_SQL
    if not _has(conn, 'project_steps'):
        return []
    deps = _has(conn, 'project_step_deps')
    managed = _has(conn, 'hb_task_manager')
    out = []
    for step_id, title, status, owner, waiting in conn.execute(
            f"SELECT step_id, title, status, COALESCE(owner,''), ({ACCEPTANCE_SQL}) FROM project_steps "
            "WHERE project_id=? AND status NOT IN ('done','skipped') ORDER BY order_idx, created_at", (project_id,)).fetchall():
        task = conn.execute("SELECT task_id, state FROM hb_tasks WHERE step_id=? AND state NOT IN ('completed','cancelled') "
                            "ORDER BY created_at DESC LIMIT 1", (step_id,)).fetchone()
        why = None
        if status == 'blocked':
            note = (conn.execute('SELECT residual_risk FROM project_steps WHERE step_id=?', (step_id,)).fetchone()[0] or '').strip()
            why = 'blocked' + (': ' + note[:90] if note else '')
        elif owner != 'apex':
            why = f'not APEX work (owner {owner or "unset"})'
        elif waiting:
            why = 'waiting for your approval'
        elif not task:
            why = 'no HB task in main chat'
        elif task[1] == 'paused' or _owner_mode(conn, task[0]) == 'off':
            why = 'held by you (Continue off)'
        elif _owner_mode(conn, task[0]) in ('on', 'auto'):
            why = 'already running on your own Continue On'
        elif managed and conn.execute("SELECT 1 FROM hb_task_manager WHERE task_id=? AND enabled=1 AND state IN "
                                      "('queued','running','needs_owner','waiting_provider','waiting_resources','waiting_dependencies')",
                                      (task[0],)).fetchone():
            why = 'already in progress with HB'
        elif task and _needs_spec(conn, task[0]):
            why = 'needs a spec: ' + _needs_spec(conn, task[0])
        elif deps:
            open_deps = [d for d, s in conn.execute(
                'SELECT d.depends_on, s.status FROM project_step_deps d JOIN project_steps s ON s.step_id=d.depends_on '
                'WHERE d.step_id=?', (step_id,)).fetchall() if s not in ('done', 'skipped')]
            if open_deps:
                why = 'waits for ' + ', '.join(open_deps)
        out.append({'step_id': step_id, 'title': str(title or ''), 'status': status,
                    'task_id': task[0] if task else None, 'skip': why})
    return out


SPEC_MARK = 'HB needs a spec:'


def vague_step(description):
    """Owner 14 Nov: a plan step with a short description and no 'Done when' line is too vague to build (APEX loops, Fred cannot help)."""
    text = str(description or '')
    return len(text) < 400 and 'Done when' not in text and 'PREPARED' not in text


def _needs_spec(conn, task_id):
    """Owner 14 Nov: a vague step only starts once it has a spec. When the CPU homework judged its card NOT ready and the step has no
    done criteria of its own, return why (else None). Steps without a card yet go ahead as before."""
    try:
        from core.hb_homework import latest
        from core.hb_dream_method import done_when
        task = hb_tasks.get(conn, task_id)
        row = conn.execute('SELECT description FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone() if task and task.get('step_id') else None
        if row and SPEC_MARK in str(row[0] or ''):
            return 'not scoped in Studio yet; HB counsel scopes it from the work that already exists'
        if not task or done_when(conn, task)[1]:
            return None
        card = latest(conn, task)
        return '; '.join(card.get('not_ready') or ['homework not ready'])[:120] if card and not card.get('ready') else None
    except Exception:
        return None


def park(conn, w, task, why, now):
    """Owner 14 Nov: a stuck step must not stop the whole list. Park it (held, in Needs-you for JD) and move on; /continue resumes it."""
    conn.execute("UPDATE hb_tasks SET state='paused', updated_at=? WHERE task_id=?", (now, task['task_id']))
    hb_tasks.event(conn, task, 'user', 'continuation_control', {'mode': 'off', 'via': 'stalled', 'actor': 'HB (stuck step parked)', 'why': why})
    hb_tasks.event(conn, task, 'hummingbird', 'workflow_left', {'project_id': w['project_id'], 'why': 'parked: ' + why})
    from core.hb_plain import message, step_name
    _post(conn, task, message(f"⏸ Parked {step_name(conn, task['step_id'], task.get('title'))}: it is stuck, so HB moves on to the next task.",
                              f"/continue {task['task_id']} gives it another go when you are ready.", details=[f"why: {why}"]))
    _update(conn, w['project_id'], task_id=None, step_id=None, stage='idle', request_id=None, note=f"Parked {task['step_id']}: {why[:100]}")


def next_ready(conn, project_id=DEFAULT_PROJECT, preferred=None):
    ready = [s for s in steps(conn, project_id) if not s['skip']]
    try:   # owner 14 Nov: HB's clipboard decides the order (pinned, then importance, then plan order)
        from core.hb_clipboard import ordered
        ready = ordered(conn, ready)
    except Exception:
        pass
    if preferred:
        chosen = [s for s in ready if s['step_id'] == preferred]
        if chosen:
            return chosen[0]
    return ready[0] if ready else None


def _post(conn, task, text):
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                       "VALUES (?,'hummingbird','user',?,'response',0)", (task['conversation_id'], text)).lastrowid
    hb_tasks.bind(conn, task['conversation_id'], mid, task_id=task['task_id'], kind='reply')
    return mid


def _manager_row(conn, task):
    from core import hb_task_manager as tm
    tm.ensure_schema(conn)
    if not conn.execute('SELECT 1 FROM hb_task_manager WHERE task_id=?', (task['task_id'],)).fetchone():
        tm.register(conn, task, next_action=task['objective'])
    cur = conn.execute('SELECT * FROM hb_task_manager WHERE task_id=?', (task['task_id'],))
    return dict(zip([d[0] for d in cur.description], tuple(cur.fetchone())))


def _queue_plan(conn, w, task, now):
    """Queue the read-only scoping turn (task manager phase 'plan'); returns the request id."""
    from core import hb_task_manager as tm
    row = _manager_row(conn, task)
    conn.execute("UPDATE hb_task_manager SET enabled=1, phase='plan', updated_at=? WHERE task_id=?", (now, task['task_id']))
    row['phase'] = 'plan'
    rid = tm._queue(conn, task, row, 'plan', 'Workflow: scope this step before any work (DREAM Distinguish)')
    _update(conn, w['project_id'], stage='planning', request_id=rid)
    return rid


def name_of(title):
    from core.hb_plain import name
    return name(title)


def start(conn, w, step, now=None):
    """Make `step` the workflow's current step: straight to execution if done criteria exist, else APEX scopes it."""
    from core.hb_dream_method import done_when
    now = time.time() if now is None else now
    task = hb_tasks.get(conn, step['task_id'])
    _update(conn, w['project_id'], task_id=task['task_id'], step_id=step['step_id'], stage='starting', request_id=None,
            preferred_step=None if w.get('preferred_step') == step['step_id'] else w.get('preferred_step'),
            note=f"Started {step['step_id']}")
    source, criteria = done_when(conn, task)
    try:   # owner 14 Nov: a READY spec card from the CPU homework replaces the GPU scoping turn
        from core.hb_homework import latest as homework_card
        card = None if criteria else homework_card(conn, task)
    except Exception:
        card = None
    if card and card.get('ready'):
        from core.hb_dream_method import set_done
        criteria = set_done(conn, task, [card['check']], f"HB homework ({card.get('model')} on the CPU; owner approved all automation)")
        _run(conn, task, w, 'Homework done on the CPU: the spec card gives the check and the plan', card.get('plan') or [])
        _update(conn, w['project_id'], stage='running')
        from core.hb_plain import message
        text = message(f"▶ Starting: {name_of(step['title'])}.", 'The homework is done (spec card from the CPU model), so APEX starts straight away.',
                       details=[f"step {step['step_id']}", f"task {task['task_id']}", f"check: {card['check']}"])
        hb_tasks.event(conn, task, 'hummingbird', 'workflow_started', {'project_id': w['project_id'], 'step_id': step['step_id'],
                                                                       'actor': w.get('actor'), 'homework': True})
        _post(conn, task, text)
        return text
    if criteria:
        _manager_row(conn, task)
        conn.execute("UPDATE hb_task_manager SET enabled=1, phase='execute', state='queued', next_due=?, detail=?, updated_at=? "
                     "WHERE task_id=?", (now, 'Workflow started it; done criteria already set', now, task['task_id']))
        _update(conn, w['project_id'], stage='running')
        from core.hb_plain import message, name
        text = message(f"▶ Starting: {name(step['title'])}.", "APEX works on it now. HB only asks you if it gets stuck.",
                       details=[f"step {step['step_id']}", f"task {task['task_id']}", f"done criteria from: {source}"])
    else:
        _queue_plan(conn, w, task, now)
        from core.hb_plain import message, name
        text = message(f"🔎 Next up: {name(step['title'])}.", "APEX is reading up on it first and will propose a short plan. Nothing changes until you approve the plan.",
                       details=[f"step {step['step_id']}", f"task {task['task_id']}"])
    hb_tasks.event(conn, task, 'hummingbird', 'workflow_started',
                   {'project_id': w['project_id'], 'step_id': step['step_id'], 'actor': w.get('actor')})
    _post(conn, task, text)
    return text


def parse_proposal(text):
    """APEX's scoping reply -> {'found': [...], 'done_when': [...], 'plan': [...]} (sections may be missing)."""
    sections, current = {}, None
    for line in str(text or '').splitlines():
        m = _SECTION.match(line)
        if m:
            key = m.group(1).lower()
            current = 'done_when' if key in ('done when', 'definition of done', 'acceptance criteria') else key
            sections.setdefault(current, [])
            if m.group(2).strip():
                sections[current].append(m.group(2))
            continue
        if current and line.strip():
            sections[current].append(line)

    def items(lines):
        out = []
        for line in lines:
            line = _BULLET.sub('', line).replace('**', '').strip(' *_')
            if len(line) >= 4:
                out.append(line[:300])
        return out
    done = items(sections.get('done_when', []))
    if len(done) == 1 and ';' in done[0]:
        done = [d.strip() for d in done[0].split(';') if len(d.strip()) >= 4]
    return {'found': items(sections.get('found', []))[:6], 'done_when': done[:8], 'plan': items(sections.get('plan', []))[:10]}


def latest_proposal(conn, task_id):
    row = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='plan_proposal' ORDER BY event_id DESC LIMIT 1",
                       (task_id,)).fetchone()
    try:
        return json.loads(row[0]) if row else None
    except (TypeError, ValueError):
        return None


def _check_plan(conn, w, task, now):
    """While APEX scopes the step: when its turn has ended, put the proposal (or the failure) in front of the owner."""
    from core import hb_task_manager as tm
    rid = w['request_id']
    work = conn.execute('SELECT state, COALESCE(stage,\'\') FROM hb_peer_work WHERE request_id=?', (rid,)).fetchone() \
        if rid and _has(conn, 'hb_peer_work') else None
    if not rid or not work or work[0] in ('queued', 'running'):
        return None
    texts = [r[0] for r in conn.execute("SELECT m.content FROM hb_peer_replies x JOIN messages m ON m.id=x.message_id "
                                        "WHERE x.request_id=? AND x.outcome='answer' ORDER BY x.message_id", (rid,))]
    proposal = parse_proposal('\n'.join(texts)) if texts else {'found': [], 'done_when': [], 'plan': []}
    tid, sid = task['task_id'], task['step_id']
    if w.get('auto_accept') and proposal['done_when']:
        # Owner 13/14 Nov: "I don't want to approve anything, it should be automatic." With auto-approve on, HB approves
        # APEX's plan itself (recorded with the owner's standing approval) and the task runs.
        from core.hb_dream_method import set_done
        hb_tasks.event(conn, task, 'apex', 'plan_proposal', {**proposal, 'request_id': rid})
        set_done(conn, task, proposal['done_when'], f"HB auto-approve ({w.get('actor') or 'owner'}: all automation approved)")
        _run(conn, task, w, 'HB approved the plan (auto-approve)', proposal.get('plan') or [])
        from core.hb_plain import message, name
        _post(conn, task, message(f"☰ Plan approved by HB: {name(task['title'])}.", 'APEX works on it now.',
                                  details=['Done when: ' + '; '.join(proposal['done_when'])]
                                  + [f'{n}. {p}' for n, p in enumerate(proposal.get('plan') or [], 1)]))
        return 'auto-approved'
    if w.get('auto_accept') and not proposal['done_when'] and conn.execute(
            "SELECT COUNT(*) FROM hb_task_events WHERE task_id=? AND kind='plan_retry'", (tid,)).fetchone()[0] < 1:
        hb_tasks.event(conn, task, 'hummingbird', 'plan_retry', {'request_id': rid, 'had_answer': bool(texts)})
        _queue_plan(conn, w, task, now)                   # one more try before JD is asked
        return 'plan retry'
    if proposal['done_when']:
        hb_tasks.event(conn, task, 'apex', 'plan_proposal', {**proposal, 'request_id': rid})
        lines = [f"APEX scoped {sid} \"{str(task['title'])[:100]}\" (workflow). Approve the plan and HB runs it."]
        for label, key, numbered in (('Found', 'found', False), ('Done when', 'done_when', False), ('Plan', 'plan', True)):
            if proposal[key]:
                lines.append(label + ':')
                lines += [(f'{n}. ' if numbered else '- ') + item for n, item in enumerate(proposal[key], 1)]
        what = '\n'.join(lines)
        options = (f'/plan {tid} approves this plan and starts the work; /done {tid} <your own criteria> replaces the criteria; '
                   f'/cancel {tid} skips this step.')
        detail = 'APEX proposed a plan; waiting for your approval'
    else:
        reason = ('its answer had no "Done when" lines' if texts else f'its turn ended without an answer ({work[0]}: {work[1][:120]})')
        what = f"APEX could not scope {sid} \"{str(task['title'])[:100]}\": {reason}."
        options = (f'/plan {tid} asks APEX again; /done {tid} <what must be true when it is finished> starts it with your criteria; '
                   f'/cancel {tid} skips this step.')
        detail = 'Scoping did not produce a plan; waiting for you'
    tm.ask_owner(conn, task, what, options, kind='plan')
    conn.execute("UPDATE hb_task_manager SET state='needs_owner', detail=?, updated_at=? WHERE task_id=?", (detail, now, tid))
    _update(conn, w['project_id'], stage='plan_ready')
    return detail


DEPENDS_RE = re.compile(r'(?m)^HB depends on:\s*(.+)$')
RESTART_RE = re.compile(r'(?m)^HB restart after:\s*(ui|all)\b')


def restart_after(conn, task, run=None):
    """Owner 14 Nov: HB drives the queue by itself, so a finished step that changes a page template or a loaded module says
    'HB restart after: ui' (or 'all') and HB restarts itself, announced ("Maintenance in progress"), once per step.
    The restart runs in the owner's user manager (systemd-run --user), so stopping the UI service does not kill it."""
    row = conn.execute('SELECT description FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone()
    found = RESTART_RE.search(row[0] or '') if row else None
    if not found or conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind='restart_requested'", (task['task_id'],)).fetchone():
        return None
    # Owner 14 Nov: three finished steps meant three restarts in two minutes ("HB is looping"). Requests now queue up and restart_tick
    # does ONE restart after RESTART_QUIET_S of quiet, naming everything it loads.
    from core.hb_plain import name
    reason = name(task.get('title') or task['step_id'])[:70]
    conn.execute('CREATE TABLE IF NOT EXISTS hb_restart_queue(task_id TEXT PRIMARY KEY, scope TEXT, reason TEXT, at REAL)')
    conn.execute('INSERT OR REPLACE INTO hb_restart_queue VALUES(?,?,?,?)', (task['task_id'], found.group(1), reason, time.time()))
    hb_tasks.event(conn, task, 'hummingbird', 'restart_requested', {'scope': found.group(1), 'reason': reason, 'queued': True})
    return found.group(1)


RESTART_QUIET_S = 60


def restart_tick(conn, now=None, run=None):
    """Launch one announced restart for all queued requests once none has arrived for RESTART_QUIET_S. Returns the scope or None."""
    if not _has(conn, 'hb_restart_queue'):
        return None
    rows = conn.execute('SELECT task_id, scope, reason, at FROM hb_restart_queue ORDER BY at').fetchall()
    now = time.time() if now is None else now
    if not rows or now - max(r[3] for r in rows) < RESTART_QUIET_S:
        return None
    try:   # owner 14 Nov: a restart never kills background work (benchmark, homework, counsel) - it waits for it
        from core import hb_background
        from core.hb_model_bench import running as bench_running
        if hb_background.snapshot() or bench_running():
            return None
    except Exception:
        pass
    import os, subprocess, sys
    from pathlib import Path
    scope = 'all' if any(r[1] == 'all' for r in rows) else 'ui'
    reason = 'Loading finished task' + ('s' if len(rows) > 1 else '') + ': ' + '; '.join(r[2] for r in rows)
    conn.execute('DELETE FROM hb_restart_queue')
    # Owner 14 Nov: never loop - the same restart reason within RESTART_REPEAT_S is refused and flagged, not repeated.
    from core.hb_loop_guard import RESTART_REPEAT_S
    conn.execute('CREATE TABLE IF NOT EXISTS hb_restart_log(reason TEXT, at REAL)')
    if conn.execute('SELECT 1 FROM hb_restart_log WHERE reason=? AND at>?', (reason, now - RESTART_REPEAT_S)).fetchone():
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (MAIN_CHAT, f'🔴 Loop stopped: HB was about to restart again for the same reason ("{reason[:120]}"). It did not; the change is already loaded.'))
        conn.commit()
        return None
    conn.execute('INSERT INTO hb_restart_log VALUES(?,?)', (reason, now))
    conn.commit()                                          # the restart must see the queue cleared and the steps closed
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'hb_restart.py'
    cmd = ['systemd-run', '--user', '--collect', '--quiet', sys.executable, str(script), scope, reason[:300]]
    env = {**os.environ, 'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'}
    (run or (lambda c: subprocess.Popen(c, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))(cmd)
    return scope


def sync_step_dependencies(conn):
    """Owner 13 Nov: when one task depends on another, it must succeed before the next starts. A plan step lists them in a line
    'HB depends on: S-xxxx, S-yyyy'; HB records them as task dependencies (hb_task_dependencies), which the task manager enforces
    (a task waits until the tasks it depends on are completed) and the workflow shows as "waits for deps". Returns rows added."""
    if not (_has(conn, 'project_steps') and _has(conn, 'hb_tasks')):
        return 0
    conn.execute('CREATE TABLE IF NOT EXISTS hb_task_dependencies(task_id TEXT NOT NULL,depends_on TEXT NOT NULL,PRIMARY KEY(task_id,depends_on))')
    added = 0
    for step_id, description in conn.execute("SELECT step_id, description FROM project_steps WHERE status NOT IN ('done','skipped') "
                                              "AND description LIKE '%HB depends on:%'").fetchall():
        found = DEPENDS_RE.search(description or '')
        if not found:
            continue
        mine = conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? AND state NOT IN ('completed','cancelled') ORDER BY created_at DESC LIMIT 1", (step_id,)).fetchone()
        if not mine:
            continue
        for needed in re.findall(r'S-[0-9A-F]{10}', found.group(1)):
            other = conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? ORDER BY created_at DESC LIMIT 1", (needed,)).fetchone()
            if other:
                added += conn.execute('INSERT OR IGNORE INTO hb_task_dependencies VALUES(?,?)', (mine[0], other[0])).rowcount
    return added


def tick(conn, now=None):
    """Coordinator tick: keep exactly one step of each enabled plan moving. Returns the texts HB posted."""
    if not _has(conn, 'hb_plan_workflow') or not _has(conn, 'hb_tasks'):
        return []
    now = time.time() if now is None else now
    posted = []
    try:
        sync_step_dependencies(conn)
    except sqlite3.OperationalError:
        pass
    try:
        restart_tick(conn, now)
    except Exception:
        pass
    cur = conn.execute('SELECT * FROM hb_plan_workflow WHERE enabled=1')
    names = [d[0] for d in cur.description]
    for w in [dict(zip(names, tuple(r))) for r in cur.fetchall()]:
        task = hb_tasks.get(conn, w['task_id']) if w['task_id'] else None
        if task:
            step = conn.execute('SELECT status FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone()
            finished = task['state'] in ('completed', 'cancelled') or not step or step[0] in ('done', 'skipped')
            held = task['state'] == 'paused' or _owner_mode(conn, task['task_id']) == 'off'
            stuck = _has(conn, 'hb_task_manager') and conn.execute(
                "SELECT detail FROM hb_task_manager WHERE task_id=? AND state='needs_owner'", (task['task_id'],)).fetchone()
            if not (finished or held) and stuck and w['stage'] in ('running', 'plan_ready') and not str(stuck[0]).startswith('Finished'):
                park(conn, w, task, str(stuck[0] or 'stuck'), now)
                w.update(task_id=None, stage='idle')
                task = None                                  # parked: go straight on to the next ready step
            elif not (finished or held):
                if w['stage'] == 'planning':
                    _check_plan(conn, w, task, now)
                elif w['stage'] == 'running' and _has(conn, 'hb_task_manager') and conn.execute(
                        'SELECT 1 FROM hb_task_manager WHERE task_id=? AND enabled=0', (task['task_id'],)).fetchone():
                    # Owner 14 Nov: "apex says it's renaming DOES but I don't think it's doing anything". The step the workflow runs
                    # must never sit parked: give it back to the task manager (back to work if it had stopped at the review gate).
                    conn.execute("UPDATE hb_task_manager SET enabled=1, state='queued', next_due=?, recovery_count=0, "
                                 "phase=CASE WHEN phase='review' THEN 'execute' ELSE phase END, detail=?, updated_at=? WHERE task_id=?",
                                 (now, 'Workflow is running it', now, task['task_id']))
                    hb_tasks.event(conn, task, 'hummingbird', 'workflow_resumed', {'why': 'its task manager row was parked'})
                continue                                  # one step at a time: the owner or the task manager has it
        if task:
            why = 'is finished' if finished else 'is held by you (Continue off), so the workflow moves on'
            if finished and step and step[0] == 'done':
                restart_after(conn, task)
            hb_tasks.event(conn, task, 'hummingbird', 'workflow_left', {'project_id': w['project_id'], 'why': why})
            if held and not finished:
                from core.hb_plain import message, step_name
                posted.append(_post(conn, task, message(f"⏸ {step_name(conn, task['step_id'], task.get('title'))} is on hold, so the plan moves on.",
                                                        "Its Keep working control starts it again.", details=[f"step {task['step_id']}", why])))
            _update(conn, w['project_id'], task_id=None, step_id=None, stage='idle', request_id=None,
                    note=f"{task['step_id']} {why}")
            w.update(task_id=None, stage='idle')
        if w['stage'] == 'finished' and now - (w['updated_at'] or 0) < FINISHED_RECHECK_S:
            continue
        step = next_ready(conn, w['project_id'], w.get('preferred_step'))
        if step:
            posted.append(start(conn, w, step, now))
        elif w['stage'] != 'finished':
            waiting = [f"{s['step_id']} ({s['skip']})" for s in steps(conn, w['project_id'])][:6]
            from core.hb_plain import message
            text = message('⏹ Nothing in the plan is ready to start right now.' if waiting else '🏁 Every step of the plan is closed.',
                           'HB starts the next step as soon as one is ready.' if waiting else '',
                           details=['waiting: ' + '; '.join(waiting)] if waiting else [])
            _update(conn, w['project_id'], stage='finished', note=text)
            mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                               "VALUES (?,'hummingbird','user',?,'response',0)", (w['conversation_id'] or MAIN_CHAT, text)).lastrowid
            posted.append(mid)
        else:
            _update(conn, w['project_id'])
    return posted


# ------------------------------------------------------------------ owner commands
def configure(conn, enabled, actor, project_id=DEFAULT_PROJECT, conversation_id=MAIN_CHAT):
    ensure_schema(conn)
    now = time.time()
    conn.execute('INSERT INTO hb_plan_workflow(project_id, enabled, conversation_id, actor, decided_at, updated_at) VALUES(?,?,?,?,?,?) '
                 'ON CONFLICT(project_id) DO UPDATE SET enabled=excluded.enabled, actor=excluded.actor, '
                 'decided_at=excluded.decided_at, conversation_id=excluded.conversation_id, updated_at=excluded.updated_at',
                 (project_id, int(bool(enabled)), conversation_id or MAIN_CHAT, actor, now, now))
    if enabled and not settings(conn, project_id)['task_id']:
        _update(conn, project_id, stage='idle')           # look for the next ready step right away
    return settings(conn, project_id)


def stop_all(conn, actor, why='Stopped by the owner'):
    """/stop also stops every plan workflow (the step it was running is held with everything else)."""
    if _has(conn, 'hb_plan_workflow'):
        conn.execute('UPDATE hb_plan_workflow SET enabled=0, actor=?, decided_at=?, note=?, updated_at=? WHERE enabled=1',
                     (actor, time.time(), why, time.time()))


def status_text(conn, project_id=DEFAULT_PROJECT):
    w = settings(conn, project_id)
    lines = [f"Workflow for {project_id}: {'ON' if w and w['enabled'] else 'off'}"
             + (f" (since {time.strftime('%d %b %H:%M', time.localtime(w['decided_at']))}, {w['actor']})" if w and w['decided_at'] else '')]
    if w and w['task_id']:
        stage = {'planning': 'APEX is scoping it', 'plan_ready': 'waiting for you to approve the plan',
                 'running': 'HB is running it', 'starting': 'starting'}.get(w['stage'], w['stage'])
        lines.append(f"- current: {w['step_id']} ({w['task_id']}): {stage}")
    plan = steps(conn, project_id)
    ready = [s for s in plan if not s['skip'] and s['step_id'] != (w or {}).get('step_id')]
    if ready:
        lines.append('- next: ' + '; '.join(f"{s['step_id']} {s['title'][:60]}" for s in ready[:3]))
    waiting = [s for s in plan if s['skip']]
    if waiting:
        lines.append('- skipped for now: ' + '; '.join(f"{s['step_id']} ({s['skip']})" for s in waiting[:8]))
    if w and w.get('auto_accept'):
        lines.append('- auto-approve: ON (steps whose checks pass are approved by HB)')
    lines.append('/workflow on | off | auto on|off | next S-xxxx (choose the next step) | status')
    return '\n'.join(lines)


def command(conn, conversation_id, args, actor, project_id=DEFAULT_PROJECT):
    sub = args[0] if args else 'status'
    if sub == 'on':
        configure(conn, True, actor, project_id, conversation_id)
        posted = tick(conn)
        return ('Workflow on. ' + ('HB started the next step; see its message.' if posted else '') + '\n' + status_text(conn, project_id)).strip()
    if sub == 'auto':
        return set_auto_accept(conn, (args[1] if len(args) > 1 else 'on') == 'on', actor, project_id)
    if sub == 'off':
        configure(conn, False, actor, project_id, conversation_id)
        return ('Workflow off. The step it was running is held with its record intact; /workflow on resumes it.\n'
                + status_text(conn, project_id))
    if sub == 'next':
        step_id = args[1]
        found = [s for s in steps(conn, project_id) if s['step_id'] == step_id]
        if not found:
            return f'{step_id} is not an open step of {project_id}.'
        if found[0]['skip']:
            return f"{step_id} cannot start: {found[0]['skip']}."
        ensure_schema(conn)
        if not settings(conn, project_id):
            configure(conn, False, actor, project_id, conversation_id)
        w = settings(conn, project_id)
        if w['task_id'] and w['step_id'] != step_id:
            hb_tasks.event(conn, hb_tasks.get(conn, w['task_id']), 'hummingbird', 'workflow_left',
                           {'project_id': project_id, 'why': f'owner chose {step_id} next'})
            _update(conn, project_id, task_id=None, step_id=None, stage='idle', request_id=None)
        _update(conn, project_id, preferred_step=step_id)
        if not w['enabled']:
            return f'{step_id} will be the next step when the workflow is on (/workflow on).'
        posted = tick(conn)
        return f'{step_id} is next.' + (' HB started it; see its message.' if posted else '') + '\n' + status_text(conn, project_id)
    return status_text(conn, project_id)


def approve_plan(conn, task_id, actor):
    """/plan T-...: the owner approves APEX's proposal (its done criteria and plan) and the task runs."""
    from core.hb_dream_method import set_done
    task = hb_tasks.get(conn, task_id)
    if not task:
        return f'No task {task_id}.'
    if task['state'] in ('completed', 'cancelled'):
        return f'{task_id} is {task["state"]}.'
    w = None
    if _has(conn, 'hb_plan_workflow'):
        cur = conn.execute('SELECT * FROM hb_plan_workflow WHERE task_id=?', (task_id,))
        row = cur.fetchone()
        w = dict(zip([d[0] for d in cur.description], tuple(row))) if row else None
    proposal = latest_proposal(conn, task_id)
    if not proposal or not proposal.get('done_when'):
        if w and w['enabled']:
            _queue_plan(conn, w, task, time.time())
            return f'Asked APEX to scope {task_id} again; HB shows you its plan when it answers.'
        return f'{task_id} has no plan from APEX to approve. Use /done {task_id} <what must be true when it is finished>.'
    criteria = set_done(conn, task, proposal['done_when'], actor + ' via /plan (APEX proposal)')
    _run(conn, task, w, 'Owner approved the plan', proposal.get('plan') or [])
    return (f"Plan approved for {task_id}. Done when: " + '; '.join(criteria) +
            '. HB is running it now and stops to ask you if it loops, keeps failing the same way, or needs review.')


def execution_scope(conn, task):
    """Work turns get the normal execution tools again; the read-only scoping limit ends with the plan approval."""
    from core.hb_task_manager import EXECUTION_TOOLS
    return hb_tasks.event(conn, task, 'hummingbird', 'tool_scope', {
        'allowed_tools': list(EXECUTION_TOOLS), 'phase': 'execute',
        'source': 'Owner approved the plan; the read-only scoping limit no longer applies'})


def _run(conn, task, w, detail, plan):
    """Leave the scoping phase: the task manager runs the task with the owner's criteria (and plan)."""
    now = time.time()
    row = _manager_row(conn, task)
    execution_scope(conn, task)
    plan_event = row['plan_event_id']
    if plan:
        plan_event = hb_tasks.event(conn, task, 'hummingbird', 'task_plan', {
            'next_action': 'Owner-approved plan:\n' + '\n'.join(f'{n}. {p}' for n, p in enumerate(plan, 1)),
            'policy': 'A model turn is a checkpoint. Work the approved plan one small step at a time.'})
    conn.execute("UPDATE hb_task_manager SET enabled=1, phase='execute', state='queued', plan_event_id=?, next_due=?, detail=?, "
                 "updated_at=? WHERE task_id=?", (plan_event, now, detail, now, task['task_id']))
    if w:
        _update(conn, w['project_id'], stage='running')


def after_done(conn, task):
    """/done on a step the workflow is scoping: the owner's own criteria replace APEX's plan and the task runs."""
    if not _has(conn, 'hb_plan_workflow') or not _has(conn, 'hb_task_manager'):
        return False
    row = conn.execute("SELECT phase FROM hb_task_manager WHERE task_id=?", (task['task_id'],)).fetchone()
    if not row or row[0] != 'plan':
        return False
    cur = conn.execute('SELECT * FROM hb_plan_workflow WHERE task_id=?', (task['task_id'],))
    found = cur.fetchone()
    w = dict(zip([d[0] for d in cur.description], tuple(found))) if found else None
    _run(conn, task, w, "Owner set the done criteria", [])
    return True
