"""HB's lights (JD 22 Nov 2026: "I want those three icons you just lit up built into HB please 'queue started' 'Inference and Continuity'"
and "build the icons and link them to DOES and DREAM"). Three groups for every APEX turn, each lit from the turn's own records - the queue,
the model calls, the tool receipts, HB's check lines and the saved reply - never from what the model says:

  TURN   Claude Code's three: ▶ queue started · ✦ inference · ∞ continuity
  DOES   Do · Operate · Execute · Sustain
  DREAM  D Distinguish · R Repetition · E Execution · A Acceleration · M Motivation

Every DOES and DREAM light carries the meaning every agent's prompt gives it, word for word (core/hb_master_prompt.DOES_DREAM_LAW,
Practice 263; a test keeps them identical), so the icon and the rule APEX works under are one thing. The words are JD's; the one-line
meanings are Claude Code's wording. turn(conn, task_id=None, request_id=None, run_id=None) -> {'request_id', 'task_id', 'turn', 'does', 'dream'}
light = {'key', 'letter', 'word', 'icon', 'law', 'state', 'why'}; state: on | live | wait | warn | bad | off"""
import json
import re
import time

LAW = {
    'do': 'Do - know the goal and the done criteria',
    'operate': "Operate - with HB's tools, records and receipts, never around them",
    'execute': 'Execute - one bounded action at a time, proved by its own check',
    'sustain': 'Sustain - leave the system working, recorded and recoverable',
    'd': 'Distinguish the goal and done',
    'r': 'Repetition - never repeat a failed action, look at past work first',
    'e': 'Execution - real tool calls with receipts',
    'a': 'Acceleration - knowledge and memory first, local first',
    'm': 'Motivation - finish',
}
LOOKUPS = {'knowledge_search', 'knowledge_read', 'memory_search', 'task_evidence', 'task_context'}
MARK = {'on': '✓', 'live': '…', 'wait': '…', 'warn': '!', 'bad': '✗', 'off': '·'}
CHECKS_BACK = ('sent the answer back', 'sent it back', 'no action this turn')


def _actions():
    try:
        from core.apex_tools import DOER_ACTIONS
        return set(DOER_ACTIONS)
    except Exception:
        return {'propose_patch', 'propose_write_file', 'run_tests', 'change_set', 'task_plan', 'studio_note', 'memory_save'}


def _payload(raw):
    try:
        value = json.loads(raw or '{}')
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _hhmm(at):
    return time.strftime('%H:%M', time.localtime(at)) if at else ''


def _light(key, letter, word, icon, state, why):
    return {'key': key, 'letter': letter, 'word': word, 'icon': icon, 'law': LAW.get(key, ''), 'state': state, 'why': str(why)[:200]}


def _passed(p):
    verdict = str(p.get('verdict') or '')
    return p.get('alm_run_status') == 'pass' or (p.get('status') == 'passed' and p.get('exit_code') == 0) or verdict.startswith('PASS')


def request_for(conn, task_id=None, run_id=None):
    """The turn's peer request: from an APEX run id (R-P<request>-...) or the task's latest request."""
    m = re.match(r'R-P(\d+)-', str(run_id or ''))
    if m:
        return int(m.group(1))
    if task_id:
        try:
            row = conn.execute('SELECT MAX(request_id) FROM hb_task_requests WHERE task_id=?', (task_id,)).fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None
    return None


def _run_rows(conn, request_id, run_id):
    try:
        if not run_id and request_id:
            row = conn.execute("SELECT run_id FROM hb_activity_log WHERE kind='start' AND run_id LIKE ? ORDER BY id DESC LIMIT 1",
                               (f'R-P{int(request_id)}-%',)).fetchone()
            run_id = row[0] if row else None
        if not run_id:
            return []
        return conn.execute('SELECT run_id, parent, kind, text, at FROM hb_activity_log WHERE run_id=? OR parent=? ORDER BY id',
                            (run_id, run_id)).fetchall()
    except Exception:
        return []


def _goal(conn, task_id):
    """(state, why) for 'know the goal and the done criteria' - shared by DOES Do and DREAM Distinguish."""
    if not task_id:
        return 'off', 'No task'
    try:
        from core import hb_tasks
        task = hb_tasks.get(conn, task_id)
    except Exception:
        task = None
    if not task:
        return 'off', 'No task'
    try:
        from core.hb_owner_intent import is_chat_task
        chat = is_chat_task(task)
    except Exception:
        chat = False
    source, criteria = None, []
    try:
        from core.hb_dream_method import done_when
        source, criteria = done_when(conn, task)
    except Exception:
        pass
    if criteria:
        return 'on', f'Done when ({source}): {criteria[0][:120]}'
    try:
        spec = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='spec_card' ORDER BY event_id DESC LIMIT 1",
                            (task_id,)).fetchone()
    except Exception:
        spec = None
    if spec:
        p = _payload(spec[0])
        return 'on', 'BA spec: ' + str(p.get('check') or p.get('goal') or '')[:120]
    if chat:
        return 'on', "JD's request is the goal"
    return 'warn', 'No done criteria for this task'


def turn(conn, task_id=None, request_id=None, run_id=None):
    request_id = request_id or request_for(conn, task_id, run_id)
    events, peer = [], None
    if request_id:
        try:
            events = [(k, _payload(p), at) for k, p, at in conn.execute(
                'SELECT kind, payload, created_at FROM hb_task_events WHERE request_id=? ORDER BY event_id', (request_id,))]
            peer = conn.execute('SELECT state, stage FROM hb_peer_work WHERE request_id=?', (request_id,)).fetchone()
            if not task_id:
                row = conn.execute('SELECT task_id FROM hb_task_requests WHERE request_id=?', (request_id,)).fetchone()
                task_id = row[0] if row else None
        except Exception:
            pass
    rows = _run_rows(conn, request_id, run_id)
    stages = [(str(p.get('stage') or ''), at) for k, p, at in events if k == 'progress']
    receipts = [(k, p) for k, p, _ in events if k in ('tool_result', 'tool_failure', 'mutation', 'test_result')]
    checks = [str(t or '') for _, _, kind, t, _ in rows if kind == 'check'] + [s for s, _ in stages if s.startswith('HB ')]
    state = peer[0] if peer else None
    run_open = bool(rows) and not any(kind in ('finish', 'error') and rid == rows[0][0] for rid, _, kind, _, _ in rows)
    running = state in ('running', 'queued', 'pending') or (state is None and run_open)
    failed = state in ('failed', 'cancelled', 'needs_review') or any(kind == 'error' and parent is None for _, parent, kind, _, _ in rows)
    why_failed = str(peer[1] if peer else '') or 'the turn ended with an error'
    interrupted = failed and 'restart' in why_failed.lower()
    saved = any(s.startswith('Agent answer saved') for s, _ in stages)
    sent_back = [c for c in checks if any(w in c for w in CHECKS_BACK)]
    ok = [p for k, p in receipts if k in ('mutation', 'test_result') or (k == 'tool_result' and p.get('status') == 'succeeded')]
    bad = [p for k, p in receipts if k == 'tool_failure' or (k == 'tool_result' and p.get('status') not in (None, 'succeeded'))]
    acts = _actions()
    real = [p for k, p in receipts if k == 'mutation' or (k == 'tool_result' and p.get('status') == 'succeeded' and p.get('tool') in acts
            and p.get('tool') != 'run_tests' and not (p.get('tool') == 'hb_tasks' and (p.get('arguments') or {}).get('action', 'list') == 'list'))]
    proofs = [p for k, p in receipts if k == 'test_result'] or [p for k, p in receipts if k == 'tool_result' and p.get('tool') == 'run_tests']
    picked = next((at for s, at in stages if s.startswith('Attached agent picked up')), None)
    busy = running and picked

    # TURN: Claude Code's three
    dispatched = next((at for k, _, at in events if k == 'dispatch'), None)
    if picked:
        waited = f' after {picked - dispatched:.0f} s in the queue' if dispatched and picked >= dispatched else ''
        q = ('on', f"Picked up from HB's queue at {_hhmm(picked)}{waited}")
    elif dispatched:
        q = ('wait', f'Queued at {_hhmm(dispatched)}, waiting its turn')
    elif rows:
        q = ('on', f'Started at {_hhmm(rows[0][4])}')
    else:
        q = ('off', 'Not queued')
    calls = [(rid, kind, text) for rid, parent, kind, text, _ in rows if parent]
    started = {rid for rid, kind, _ in calls if kind == 'start'}
    ended = {rid for rid, kind, _ in calls if kind in ('finish', 'error')}
    tokens = sum(int(m.group(1)) for _, kind, text in calls if kind == 'finish' for m in [re.match(r'(\d+) tokens', str(text or ''))] if m)
    rounds = len([s for s, _ in stages if s.startswith('APEX thinking - round')])
    if started - ended and running:
        inf = ('live', f'The model is reading or writing now (call {len(started)})')
    elif started or rounds:
        inf = ('on', f'{len(started) or rounds} model call(s)' + (f', {tokens} tokens written' if tokens else ''))
    elif busy:
        inf = ('live', 'Starting the model')
    else:
        inf = ('off', 'No model call yet')
    nxt = False
    if task_id and request_id:
        try:
            nxt = bool(conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind IN ('continuation_queued','resume_queued') "
                                    "AND COALESCE(request_id,0)>? LIMIT 1", (task_id, request_id)).fetchone())
        except Exception:
            pass
    carried = 'DREAM card and task history carried in' if task_id and dispatched else 'chat history carried in'
    if failed:
        cont = ('warn' if interrupted else 'bad', f'{carried}; {why_failed[:120]}')
    elif saved:
        cont = ('on', f'{carried}; answer saved and read back' + ('; next turn queued' if nxt else ''))
    elif running:
        cont = ('live', carried)
    else:
        cont = ('off', 'Nothing carried yet')
    turn_lights = [_light('queue', 'Q', 'queue started', '▶', *q), _light('inference', 'I', 'inference', '✦', *inf),
                   _light('continuity', 'C', 'continuity', '∞', *cont)]

    # DOES
    goal = _goal(conn, task_id)
    if ok:
        operate = ('on', f'{len(ok)} tool call(s) with receipts' + (f', {len(bad)} failed' if bad else ''))
    elif bad:
        operate = ('bad', f'{len(bad)} tool call(s), all failed')
    else:
        operate = ('live' if busy else 'off', 'No tool call yet')
    if proofs and real:
        execute = (('on', f"{', '.join(sorted({str(p.get('tool') or 'change') for p in real}))[:80]} proved by its check") if any(_passed(p) for p in proofs)
                   else ('bad', 'Its check failed'))
    elif real:
        execute = ('warn', f"Acted ({', '.join(sorted({str(p.get('tool') or 'change') for p in real}))[:80]}), not proved by a check yet")
    elif proofs:
        execute = ('on' if any(_passed(p) for p in proofs) else 'bad', 'A check ran: ' + ('passed' if any(_passed(p) for p in proofs) else 'failed'))
    elif ok:
        execute = ('warn', f'No action yet, only reads ({len(ok)})')
    else:
        execute = ('live' if busy else 'off', 'No action yet')
    if failed:
        sustain = ('warn' if interrupted else 'bad', why_failed[:160])
    elif saved:
        sustain = ('on', 'Result recorded and read back' + ('; the task carries on next turn' if nxt else ''))
    elif running:
        sustain = ('live', 'Working')
    else:
        sustain = ('off', 'Nothing recorded yet')
    does = [_light('do', 'D', 'Do', 'Do', *goal), _light('operate', 'O', 'Operate', 'Operate', *operate),
            _light('execute', 'E', 'Execute', 'Execute', *execute), _light('sustain', 'S', 'Sustain', 'Sustain', *sustain)]

    # DREAM
    failed_calls = {}
    for p in bad:
        key = (p.get('tool'), json.dumps(p.get('arguments') or {}, sort_keys=True))
        failed_calls[key] = failed_calls.get(key, 0) + 1
    repeated = [k[0] for k, n in failed_calls.items() if n > 1]
    stopped = [c for c in checks if 'repeat' in c.lower()]
    if repeated:
        r = ('bad', f'Repeated a failed action: {repeated[0]}')
    elif stopped:
        r = ('warn', stopped[-1][:160])
    elif receipts:
        r = ('on', 'No failed action repeated')
    else:
        r = ('off', 'No action yet')
    e = operate if operate[0] != 'on' else ('on', f'{len(ok)} real tool call(s) with receipts')
    looked = sorted({str(p.get('tool')) for _, p in receipts if p.get('tool') in LOOKUPS})
    a = ('on', 'Looked first in: ' + ', '.join(looked)) if looked else ('off', 'KC and memory not used this turn')
    if failed:
        m = ('bad', 'The turn did not finish')
    elif saved:
        m = ('warn', f'Finished after HB sent the answer back: {sent_back[-1][:120]}') if sent_back else ('on', 'Finished and reported')
    elif sent_back:
        m = ('warn', sent_back[-1][:160])
    elif running:
        m = ('live', 'Working')
    else:
        m = ('off', 'Not finished')
    dream = [_light('d', 'D', 'Distinguish', 'D', *goal), _light('r', 'R', 'Repetition', 'R', *r), _light('e', 'E', 'Execution', 'E', *e),
             _light('a', 'A', 'Acceleration', 'A', *a), _light('m', 'M', 'Motivation', 'M', *m)]
    return {'request_id': request_id, 'task_id': task_id, 'turn': turn_lights, 'does': does, 'dream': dream}


def chat_line(lights):
    """'▶✓ ✦✓ ∞✓ · DOES D✓ O✓ E! S✓ · DREAM D✓ R✓ E✓ A· M✓' for HB's main-chat lines (Telegram reads it too)."""
    if not lights or not lights.get('turn'):
        return ''
    mark = lambda l: MARK.get(l['state'], '·')
    return (' '.join(l['icon'] + mark(l) for l in lights['turn']) + ' · DOES ' + ' '.join(l['letter'] + mark(l) for l in lights['does'])
            + ' · DREAM ' + ' '.join(l['letter'] + mark(l) for l in lights['dream']))


def why_line(lights):
    """The DOES and DREAM lights that are not on, with their reason - one short line (empty when everything is on)."""
    out = [f"{l['word']}: {l['why']}" for l in (lights or {}).get('does', []) + (lights or {}).get('dream', []) if l['state'] in ('warn', 'bad', 'off')]
    return '; '.join(out)[:300]
