"""DOES and DREAM lights (JD 22 Nov 2026: "I want those three icons you just lit up built into HB please 'queue started' 'Inference and
Continuity' ... DOES, Do Operate Execute Sustain is the same thing but I want it built into HB as icons so I can see the system actually
using DREAM to do its work").

Claude Code shows a turn as lights: the queue picked it up, the model is inferring, continuity (memory, history) came along. An HB turn
is the same, as DOES, and the DREAM method shows as five more lights. Every light comes from what the turn really did - the queue,
the model calls, the tool receipts, HB's own check lines and the saved reply - never from the prompt text.

  DOES   Do ▶ queue started · Operate ✦ inference · Execute ⚙ actions with receipts · Sustain ∞ continuity
  DREAM  D done criteria known · R no failed action repeated · E a real action (change, test, plan), not only reading ·
         A KC and memory looked at first · M reported in its own words, not sent back by HB

  turn(conn, task_id=None, request_id=None, run_id=None) -> {'request_id', 'task_id', 'does': [light], 'dream': [light]}
  light = {'key', 'letter', 'word', 'icon', 'state', 'why'};  state: on | live | wait | warn | bad | off
  chat_line(lights) -> 'DOES ▶✓ ✦✓ ⚙✓ ∞✓ · DREAM D✓ R! E! A· M✓' for HB's main-chat lines (Telegram reads it too)"""
import json
import re
import time

DOES = (('do', 'Do', '▶', 'queue started'), ('operate', 'Operate', '✦', 'inference'), ('execute', 'Execute', '⚙', 'actions with receipts'),
        ('sustain', 'Sustain', '∞', 'continuity'))
DREAM = (('d', 'D', 'Distinguish'), ('r', 'R', 'Repetition'), ('e', 'E', 'Execution'), ('a', 'A', 'Acceleration'), ('m', 'M', 'Motivation'))
LOOKUPS = {'knowledge_search', 'knowledge_read', 'memory_search', 'task_evidence', 'task_context'}
MARK = {'on': '✓', 'live': '…', 'wait': '…', 'warn': '!', 'bad': '✗', 'off': '·'}
CHECKS_BACK = ('sent the answer back', 'sent it back')


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
    return {'key': key, 'letter': letter, 'word': word, 'icon': icon, 'state': state, 'why': str(why)[:200]}


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
    checks = [str(t or '') for _, _, kind, t, _ in rows if kind == 'check']
    checks += [s for s, _ in stages if s.startswith('HB ')]
    state = peer[0] if peer else None
    run_open = bool(rows) and not any(kind in ('finish', 'error') and rid == rows[0][0] for rid, _, kind, _, _ in rows)
    running = state in ('running', 'queued', 'pending') or (state is None and run_open)
    failed = state in ('failed', 'cancelled', 'needs_review') or any(kind == 'error' and parent is None for _, parent, kind, _, _ in rows)

    # DOES · Do: queue started
    dispatched = next((at for k, _, at in events if k == 'dispatch'), None)
    picked = next((at for s, at in stages if s.startswith('Attached agent picked up')), None)
    if picked:
        waited = f' after {picked - dispatched:.0f} s in the queue' if dispatched and picked >= dispatched else ''
        do = _light('do', 'Do', 'Do · queue started', '▶', 'on', f'Picked up from HB\'s queue at {_hhmm(picked)}{waited}')
    elif dispatched:
        do = _light('do', 'Do', 'Do · queue started', '▶', 'wait', f'Queued at {_hhmm(dispatched)}, waiting its turn')
    elif rows:
        do = _light('do', 'Do', 'Do · queue started', '▶', 'on', f'Started at {_hhmm(rows[0][4])}')
    else:
        do = _light('do', 'Do', 'Do · queue started', '▶', 'off', 'Not queued')

    # DOES · Operate: inference
    calls = [(rid, kind, text) for rid, parent, kind, text, _ in rows if parent]
    started = {rid for rid, kind, text in calls if kind == 'start'}
    ended = {rid for rid, kind, _ in calls if kind in ('finish', 'error')}
    tokens = sum(int(m.group(1)) for _, kind, text in calls if kind == 'finish' for m in [re.match(r'(\d+) tokens', str(text or ''))] if m)
    rounds = len([s for s, _ in stages if s.startswith('APEX thinking - round')])
    if started - ended and running:
        op = _light('operate', 'Operate', 'Operate · inference', '✦', 'live', f'The model is reading or writing now (call {len(started)})')
    elif started or rounds:
        n = len(started) or rounds
        op = _light('operate', 'Operate', 'Operate · inference', '✦', 'on', f'{n} model call(s)' + (f', {tokens} tokens written' if tokens else ''))
    elif running and picked:
        op = _light('operate', 'Operate', 'Operate · inference', '✦', 'live', 'Starting the model')
    else:
        op = _light('operate', 'Operate', 'Operate · inference', '✦', 'off', 'No model call yet')

    # DOES · Execute: tool actions with receipts
    ok = [p for k, p in receipts if k in ('mutation', 'test_result') or (k == 'tool_result' and p.get('status') == 'succeeded')]
    bad = [p for k, p in receipts if k == 'tool_failure' or (k == 'tool_result' and p.get('status') not in (None, 'succeeded'))]
    if ok:
        ex = _light('execute', 'Execute', 'Execute · receipts', '⚙', 'on', f'{len(ok)} tool action(s) with receipts' + (f', {len(bad)} failed' if bad else ''))
    elif bad:
        ex = _light('execute', 'Execute', 'Execute · receipts', '⚙', 'bad', f'{len(bad)} tool action(s), all failed')
    else:
        ex = _light('execute', 'Execute', 'Execute · receipts', '⚙', 'live' if running and picked else 'off', 'No tool action yet')

    # DOES · Sustain: continuity in (DREAM card, history) and out (saved, read back, next turn queued)
    saved = any(s.startswith('Agent answer saved') for s, _ in stages)
    nxt = False
    if task_id and request_id:
        try:
            nxt = bool(conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind IN ('continuation_queued','resume_queued') "
                                    "AND COALESCE(request_id,0)>? LIMIT 1", (task_id, request_id)).fetchone())
        except Exception:
            pass
    carried = 'DREAM card and task history carried in' if task_id and dispatched else 'chat history carried in'
    if failed:
        why = str(peer[1] if peer else '') or 'the turn ended with an error'
        su = _light('sustain', 'Sustain', 'Sustain · continuity', '∞', 'warn' if 'restart' in why.lower() else 'bad', f'{carried}; {why[:120]}')
    elif saved:
        su = _light('sustain', 'Sustain', 'Sustain · continuity', '∞', 'on', f'{carried}; answer saved and read back' + ('; next turn queued' if nxt else ''))
    elif running:
        su = _light('sustain', 'Sustain', 'Sustain · continuity', '∞', 'live', carried)
    else:
        su = _light('sustain', 'Sustain', 'Sustain · continuity', '∞', 'off', 'Nothing carried yet')

    # DREAM
    task = None
    if task_id:
        try:
            from core import hb_tasks
            task = hb_tasks.get(conn, task_id)
        except Exception:
            task = None
    d_state, d_why = 'off', 'No task'
    if task:
        try:
            from core.hb_owner_intent import is_chat_task
            chat = is_chat_task(task)
        except Exception:
            chat = False
        source, criteria = (None, [])
        try:
            from core.hb_dream_method import done_when
            source, criteria = done_when(conn, task)
        except Exception:
            pass
        spec = None
        try:
            spec = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='spec_card' ORDER BY event_id DESC LIMIT 1",
                                (task_id,)).fetchone()
        except Exception:
            pass
        if criteria:
            d_state, d_why = 'on', f'Done when ({source}): {criteria[0][:120]}'
        elif spec:
            d_state, d_why = 'on', 'Homework spec card: ' + str(_payload(spec[0]).get('check') or _payload(spec[0]).get('goal') or '')[:120]
        elif chat:
            d_state, d_why = 'on', "JD's request is the goal"
        else:
            d_state, d_why = 'warn', 'No done criteria for this task'
    d = _light('d', 'D', 'Distinguish', 'D', d_state, d_why)

    failed_calls = {}
    for p in bad:
        key = (p.get('tool'), json.dumps(p.get('arguments') or {}, sort_keys=True))
        failed_calls[key] = failed_calls.get(key, 0) + 1
    repeated = [k[0] for k, n in failed_calls.items() if n > 1]
    stopped = [c for c in checks if 'repeat' in c.lower()]
    if repeated:
        r = _light('r', 'R', 'Repetition', 'R', 'bad', f'Repeated a failed action: {repeated[0]}')
    elif stopped:
        r = _light('r', 'R', 'Repetition', 'R', 'warn', stopped[-1][:160])
    elif receipts:
        r = _light('r', 'R', 'Repetition', 'R', 'on', 'No failed action repeated')
    else:
        r = _light('r', 'R', 'Repetition', 'R', 'off', 'No action yet')

    acts = _actions()
    real = [p for k, p in receipts if k in ('mutation', 'test_result') or (k == 'tool_result' and p.get('status') == 'succeeded'
            and p.get('tool') in acts and not (p.get('tool') == 'hb_tasks' and (p.get('arguments') or {}).get('action', 'list') == 'list'))]
    if real:
        e = _light('e', 'E', 'Execution', 'E', 'on', f"{len(real)} real action(s): " + ', '.join(sorted({str(p.get('tool') or 'change') for p in real}))[:120])
    elif ok:
        e = _light('e', 'E', 'Execution', 'E', 'warn', f'Only read so far ({len(ok)} read(s)), no change, test or plan')
    else:
        e = _light('e', 'E', 'Execution', 'E', 'live' if running and picked else 'off', 'No action yet')

    looked = sorted({str(p.get('tool')) for _, p in receipts if p.get('tool') in LOOKUPS})
    a = (_light('a', 'A', 'Acceleration', 'A', 'on', 'Looked first in: ' + ', '.join(looked)) if looked else
         _light('a', 'A', 'Acceleration', 'A', 'off', 'KC and memory not used this turn'))

    sent_back = [c for c in checks if any(w in c for w in CHECKS_BACK)]
    if failed:
        m = _light('m', 'M', 'Motivation', 'M', 'bad', 'The turn ended without a report')
    elif saved:
        m = (_light('m', 'M', 'Motivation', 'M', 'warn', f'Reported after HB sent {len(sent_back)} answer(s) back: {sent_back[-1][:120]}') if sent_back
             else _light('m', 'M', 'Motivation', 'M', 'on', 'Reported in main chat'))
    elif sent_back:
        m = _light('m', 'M', 'Motivation', 'M', 'warn', sent_back[-1][:160])
    elif running:
        m = _light('m', 'M', 'Motivation', 'M', 'live', 'Working')
    else:
        m = _light('m', 'M', 'Motivation', 'M', 'off', 'No report yet')
    return {'request_id': request_id, 'task_id': task_id, 'does': [do, op, ex, su], 'dream': [d, r, e, a, m]}


def chat_line(lights):
    if not lights or not lights.get('does'):
        return ''
    does = ' '.join(l['icon'] + MARK.get(l['state'], '·') for l in lights['does'])
    dream = ' '.join(l['letter'] + MARK.get(l['state'], '·') for l in lights['dream'])
    return f'DOES {does} · DREAM {dream}'


def why_line(lights):
    """The lights that are not on, with their reason - one short line (empty when everything is on)."""
    out = [f"{l['word'].split(' ·')[0]}: {l['why']}" for l in (lights or {}).get('dream', []) if l['state'] in ('warn', 'bad', 'off')]
    return '; '.join(out)[:300]
