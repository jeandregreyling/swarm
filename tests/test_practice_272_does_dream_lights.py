"""Practice 272 (JD 22 Nov 2026: "I want those three icons ... 'queue started' 'Inference and Continuity' built into HB ... so I can see the
system actually using DREAM to do its work", and "ensure that apex doesn't give me more 'fuck you dude' answers"): every APEX turn gets
DOES and DREAM lights from its own records, HB Live shows them, the finished line carries them, and a pasted tool dump is sent back."""
import json
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from core import hb_activity_log, hb_announce, hb_lights, hb_live, hb_tasks
from core.apex_tools import DUMP_NOTICE, pasted_output

ROOT = Path(__file__).resolve().parents[1]
JD_09_01 = ("The grep_repo tool found the API endpoints in the hb-live.js file. Here are the relevant lines:\n\n"
            "frontend/static/js/hb-live.js:8:\n    GET /api/peer/v1/hb/live, every 2 s while the page is visible and at once on a chat event.\n\n"
            "frontend/static/js/hb-live.js:483:\n    return url ? fetch(url, requestOptions) : fetch('/api/peer/v1/hb/queue', requestOptions);")
GREP = {'tool': 'grep_repo', 'status': 'succeeded', 'arguments': {'query': 'API', 'path': 'frontend/static/js/hb-live.js'},
        'output': "frontend/static/js/hb-live.js:8:    GET /api/peer/v1/hb/live, every 2 s while the page is visible and at once on a chat event.\n"
                  "frontend/static/js/hb-live.js:483:    return url ? fetch(url, requestOptions) : fetch('/api/peer/v1/hb/queue', requestOptions);"}
WORK = '{"task_type": "hb_owner_resumed", "task_id": "T-53BA88A80354", "next_task": "Current plan (do this first): Studio step S-4BD96DF6D4"}'


def _db():
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    hb_activity_log.ensure(c)
    c.execute('CREATE TABLE hb_peer_work(request_id INTEGER PRIMARY KEY, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    c.execute('CREATE TABLE peer_messages(id INTEGER PRIMARY KEY, recipient TEXT, conversation_id INT)')
    c.execute("INSERT INTO hb_tasks(task_id, conversation_id, root_message_id, title, objective, step_id) VALUES "
              "('T-1', 2845, 1, 'Discoverable UI controls', 'Expose the live-pane controls.\nDone when: the API lists every control', 'S-1')")
    return c


def _turn(c, rid, state, events, task='T-1'):
    c.execute('INSERT INTO hb_task_requests(request_id, task_id) VALUES (?,?)', (rid, task))
    c.execute('INSERT INTO hb_peer_work VALUES (?,?,?,?,?)', (rid, 'apex', state, 'x', time.time()))
    c.execute("INSERT INTO peer_messages VALUES (?, 'apex', 2845)", (rid,))
    at = 1000.0
    for kind, payload in events:
        at += 1
        c.execute('INSERT INTO hb_task_events(task_id, agent, kind, request_id, payload, created_at) VALUES (?,?,?,?,?,?)',
                  (task, 'apex', kind, rid, json.dumps(payload), at))


def _progress(stage):
    return ('progress', {'status': 'running', 'stage': stage})


START = [('dispatch', {'recipient': 'apex'}), _progress('Attached agent picked up the explicitly addressed request'),
         _progress('APEX thinking - round 1')]
SAVED = _progress('Agent answer saved and read back in main chat')


def _states(lights):
    return [l['state'] for l in lights['does']], {l['letter']: l['state'] for l in lights['dream']}


def test_a_reading_only_turn_lights_does_but_shows_E_amber_and_A_dark():
    c = _db()
    _turn(c, 7, 'completed', START + [('tool_result', GREP), SAVED])
    lights = hb_lights.turn(c, request_id=7)
    does, dream = _states(lights)
    assert does == ['on', 'on', 'on', 'on']
    assert dream == {'D': 'on', 'R': 'on', 'E': 'warn', 'A': 'off', 'M': 'on'}
    assert hb_lights.chat_line(lights) == 'DOES ▶✓ ✦✓ ⚙✓ ∞✓ · DREAM D✓ R✓ E! A· M✓'
    assert 'Only read so far' in hb_lights.why_line(lights) and 'KC and memory not used' in hb_lights.why_line(lights)
    assert 'Done when (task): the API lists every control' == lights['dream'][0]['why']


def test_a_running_turn_pulses_inference_while_the_model_call_is_open():
    c = _db()
    _turn(c, 8, 'running', START)
    c.execute("INSERT INTO hb_activity_log(at, run_id, parent, lane, actor, kind, text) VALUES (1001,'R-P8-ABC123',NULL,'gpu','apex','start','APEX: x')")
    c.execute("INSERT INTO hb_activity_log(at, run_id, parent, lane, actor, kind, text) VALUES (1002,'R-C1','R-P8-ABC123','gpu','apex','start','model call')")
    lights = hb_lights.turn(c, run_id='R-P8-ABC123')
    does, dream = _states(lights)
    assert lights['request_id'] == 8 and lights['task_id'] == 'T-1'
    assert does[0] == 'on' and does[1] == 'live' and does[3] == 'live' and dream['M'] == 'live'


def test_queued_but_not_picked_up_waits_on_do():
    c = _db()
    _turn(c, 9, 'running', [('dispatch', {'recipient': 'apex'})])
    assert hb_lights.turn(c, request_id=9)['does'][0]['state'] == 'wait'


def test_repeats_and_sent_back_answers_show_amber_or_red():
    c = _db()
    fail = {'tool': 'read_file', 'arguments': {'path': 'ui/hummingbird.py'}, 'error': 'not found'}
    _turn(c, 10, 'completed', START + [('tool_failure', fail), ('tool_failure', fail), _progress('HB DOES check sent the answer back: it pasted tool output'), SAVED])
    _, dream = _states(hb_lights.turn(c, request_id=10))
    assert dream['R'] == 'bad' and dream['M'] == 'warn'
    _turn(c, 11, 'completed', START + [('tool_result', GREP), _progress('HB stopped a repeat: that read already ran this turn'), SAVED])
    lights = hb_lights.turn(c, request_id=11)
    assert _states(lights)[1]['R'] == 'warn' and 'stopped a repeat' in lights['dream'][1]['why']


def test_real_action_and_kc_lookup_light_E_and_A():
    c = _db()
    _turn(c, 12, 'completed', START + [('tool_result', {'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'hb live'}}),
                                       ('tool_result', {'tool': 'propose_patch', 'status': 'succeeded', 'arguments': {'file_path': 'core/x.py'}}),
                                       ('test_result', {'alm_run_status': 'pass'}), SAVED])
    _, dream = _states(hb_lights.turn(c, request_id=12))
    assert dream == {'D': 'on', 'R': 'on', 'E': 'on', 'A': 'on', 'M': 'on'}


def test_a_failed_turn_is_red_on_sustain_and_motivation():
    c = _db()
    _turn(c, 13, 'failed', START)
    does, dream = _states(hb_lights.turn(c, request_id=13))
    assert does[3] == 'bad' and dream['M'] == 'bad'


def test_live_snapshot_puts_lights_on_apex_cards_and_the_meter_only():
    c = _db()
    _turn(c, 14, 'running', START + [('tool_result', GREP)])
    items = [{'lane': 'gpu', 'run_id': 'P-14', 'task_id': 'T-1'}, {'lane': 'claude-code', 'run_id': 'R-XYZ', 'task_id': None}]
    hb_live._with_lights(c, items)
    assert items[0]['lights']['request_id'] == 14 and 'lights' not in items[1]
    meter = hb_live._apex_lights(c)
    assert meter['request_id'] == 14 and meter['running'] is True


def test_the_finished_line_carries_the_lights_and_what_was_not_lit():
    c = _db()
    _turn(c, 15, 'completed', START + [('tool_result', GREP), SAVED])
    line = hb_announce._lit(c, 'P-15')
    assert line.startswith('\nDOES ▶✓ ✦✓ ⚙✓ ∞✓ · DREAM D✓ R✓ E! A· M✓') and 'Only read so far' in line
    assert hb_announce._lit(c, 'P-999') == '' and hb_announce._lit(c, 'R-OLDSTYLE') == ''


def test_jds_09_01_grep_dump_is_sent_back_and_real_answers_are_not():
    assert pasted_output(JD_09_01, [GREP], WORK)
    assert not pasted_output(JD_09_01, [GREP, {'tool': 'propose_patch', 'status': 'succeeded'}], WORK)
    assert not pasted_output(JD_09_01, [GREP], 'show me the lines in hb-live.js that call the API')
    own = ("I read hb-live.js: the page polls /api/peer/v1/hb/live every 2 s, and the queue actions post to /api/peer/v1/hb/queue. "
           "So the controls already have endpoints; what is missing is a list of them for local agents. I saved that as the plan and "
           "the next step is a read-only /api/peer/v1/hb/controls that returns each button with its action.\n"
           "frontend/static/js/hb-live.js:8: GET /api/peer/v1/hb/live")
    assert not pasted_output(own, [GREP], WORK)
    assert 'not the lines' in DUMP_NOTICE and 'task_plan' in DUMP_NOTICE and 'own words' in DUMP_NOTICE


def test_apex_turn_run_id_names_its_request_and_the_checks_are_wired():
    src = (ROOT / 'core/apex_tools.py').read_text()
    assert "run_id = f'R-P{int(request)}-" in src and "run_id=run_id) as r:" in src
    assert 'pasted_output(answer, receipts, latest_user)' in src and "say_step('HB stopped a repeat:" in src
    assert hb_lights.request_for(None, run_id='R-P3129-ABCDEF') == 3129


def _node(expr, snap):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    js = ROOT / 'frontend/static/js/hb-live.js'
    code = f"const R=require({json.dumps(str(js))}); const snap={json.dumps(snap)}; process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def test_the_page_shows_the_lights_on_the_meter_and_the_apex_card():
    c = _db()
    _turn(c, 16, 'completed', START + [('tool_result', GREP), SAVED])
    lights = hb_lights.turn(c, request_id=16)
    snap = {'at': 1000, 'apex_live': {'up': True, 'busy': False, 'prompt_tokens': 10}, 'apex_lights': dict(lights, running=False),
            'lanes': [{'id': 'gpu', 'state': 'busy', 'items': [{'actor': 'apex', 'title': 'APEX: UI controls', 'lights': lights, 'trail': []}]}],
            'needs_you': [], 'master': {'items': []}, 'history': []}
    html = _node('R.renderBoard(snap, {})', snap)
    meter = html.split('hbl-pane-head')[0]
    for word in ('last turn', 'DOES', 'queue started', 'inference', 'continuity', 'DREAM', 'hbl-l-warn', 'hbl-l-off', 'hbl-l-on'):
        assert word in meter, word
    assert html.count('class="hbl-lights"') == 2            # the meter and the APEX card
    assert 'Only read so far' in _node('R.renderLights(snap.apex_lights)', snap)
    assert _node('R.renderLights(null)', snap) == ''
