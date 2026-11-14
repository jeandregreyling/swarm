"""Owner 14 Nov: applause only for real success; corrections as the better way (lessons, not blame); try-better on negative feedback;
capability tags and badges; a daily thank-you, not a ranking."""
import json
import time

from core import hb_tasks, hb_merits, hb_commands as hc, peer_bridge
from test_peer_turns import flow, reply  # noqa: F401
from test_hb_plan_workflow import plan, P  # noqa: F401


def _request(conn, task, model):
    rid = peer_bridge.enqueue(conn, 1, task['root_message_id'], 'work ' + model + str(time.time()), ['apex'], sender='hummingbird')[0]
    hb_tasks.event(conn, task, 'apex', 'progress', {'stage': 'Local model selected: ' + model}, request_id=rid)
    return rid


def _said(conn):
    return [r[0] for r in conn.execute("SELECT content FROM messages WHERE from_agent='hummingbird' ORDER BY id")]


def test_applause_only_for_a_checked_success_and_credit_goes_to_who_did_it(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A5'])
    rid = _request(conn, task, 'qwen2.5:14b-instruct')
    hb_tasks.event(conn, task, 'apex', 'mutation', {'output': 'Approved patch completed: core/x.py; SHA'}, request_id=rid)
    hb_tasks.event(conn, task, 'apex', 'test_result', {'alm_run_status': 'pass', 'verdict': 'PASS: 3 passed'}, request_id=rid)
    hc.accept_step(conn, 'S-00000000A5', 'jd')
    assert any(s.startswith('🌺 HB gives APEX (qwen2.5:14b-instruct) a flower') and '(+3 coder)' in s for s in _said(conn))
    p = hb_merits.profile(conn)[0]
    assert p['role'] == 'APEX' and p['success'] == {'coder': 1} and p['badges'] == {'coder': 'I'} and p['tags'] == []


def test_no_check_no_applause(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A2'])
    rid = _request(conn, task, 'qwen2.5:14b-instruct')
    hb_tasks.event(conn, task, 'apex', 'mutation', {'output': 'Approved patch completed: core/x.py'}, request_id=rid)
    hc.accept_step(conn, 'S-00000000A2', 'jd')                                  # accepted, but no passing check after the change
    assert not any(s.startswith('🌺') for s in _said(conn)) and hb_merits.profile(conn) == []


def test_a_fix_by_fred_is_recorded_as_the_better_way_and_shown_to_apex(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A5'])
    stuck = _request(conn, task, 'qwen2.5:14b-instruct')
    hb_tasks.event(conn, task, 'apex', 'tool_failure', {'tool': 'propose_patch', 'error': 'Exact patch text matched 0 locations'}, request_id=stuck)
    fred = _request(conn, task, 'fred-cpu:24b')
    hb_tasks.event(conn, task, 'hummingbird', 'fred_turn', {'model': 'fred-cpu:24b'}, request_id=fred)
    hb_tasks.event(conn, task, 'apex', 'mutation', {'output': 'Approved patch completed: core/x.py'}, request_id=fred)
    hb_tasks.event(conn, task, 'apex', 'reply', {'content': 'Fred: the old text had changed; I patched the current line and the check passes.'}, request_id=fred)
    conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?", (fred,))
    assert hb_merits.corrections(conn) == 1 and hb_merits.corrections(conn) == 0          # once
    assert any(s.startswith('🌺 APEX gives Fred a flower for the fix on') for s in _said(conn))
    lesson = hb_merits.lessons(conn)[0]
    assert 'What went wrong: Exact patch text matched 0 locations' in lesson and 'The better way: Fred: the old text had changed' in lesson
    from core.hb_dream_method import card
    assert 'Learned from a correction: What went wrong' in card(conn, task)
    p = {x['role']: x for x in hb_merits.profile(conn)}
    assert p['Fred']['fixes'] == 1 and p['APEX']['lessons'] == 1


def test_negative_feedback_is_try_better_and_nothing_stops(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A1'])
    _request(conn, task, 'qwen2.5:14b-instruct')
    assert hb_merits.try_better(conn, 'not good enough') == 1
    assert hb_tasks.get(conn, task['task_id'])['state'] != 'paused'
    assert '1 try-better notes' in hb_merits.status_text(conn)


def test_tags_badges_and_the_daily_thank_you(plan):
    conn, _, _ = plan
    for n in range(5):
        hb_merits._add(conn, 'success', 'APEX', 'qwen2.5:14b-instruct', category='coder', ref=f't{n}')
    hb_merits._add(conn, 'correction', 'Fred', 'fred-cpu:24b', ref='r1')
    p = {x['role']: x for x in hb_merits.profile(conn)}
    assert p['APEX']['tags'] == ['coder'] and p['APEX']['badges'] == {'coder': 'II'}
    evening = time.mktime(time.localtime()[:3] + (20, 0, 0, 0, 0, -1))
    mid = hb_merits.daily(conn, now=evening)
    text = conn.execute('SELECT content FROM messages WHERE id=?', (mid,)).fetchone()[0]
    assert text.startswith('🌺 End-of-day flowers from HB - thank you, APEX (qwen2.5:14b-instruct): 5 task(s) done')
    assert 'Fred (fred-cpu:24b): 0 task(s) done, 1 fix(es) for others' in text and 'Biggest help today: APEX' in text
    assert hb_merits.daily(conn, now=evening + 60) is None                      # once a day
    assert 'coder II' in hc.handle(conn, 1, '/merits', 'jd')
