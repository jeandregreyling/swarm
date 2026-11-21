"""Practice 274 (JD 22 Nov 09:3x: "build the icons and link them to DOES and DREAM", "is this 'lets make shit up as we go along' day?"):
Practice 272 mapped Claude Code's icons onto DOES with made-up meanings (Do = queue started). Now Claude Code's three icons are their own
group, and every DOES and DREAM icon is lit by the meaning every agent's prompt gives it (core/hb_master_prompt.py,
Practice 263), carried word for word. The meanings are Claude Code's wording of JD's DOES and DREAM words."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core import hb_activity_log, hb_lights, hb_tasks
from core.hb_master_prompt import DOES_DREAM_LAW

ROOT = Path(__file__).resolve().parents[1]


def test_every_does_and_dream_icon_carries_its_prompt_meaning_word_for_word():
    assert set(hb_lights.LAW) == {'do', 'operate', 'execute', 'sustain', 'd', 'r', 'e', 'a', 'm'}
    for key, text in hb_lights.LAW.items():
        assert text in DOES_DREAM_LAW, key


def _db(events, state='completed'):
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    hb_activity_log.ensure(c)
    c.execute('CREATE TABLE hb_peer_work(request_id INTEGER PRIMARY KEY, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    c.execute("INSERT INTO hb_tasks(task_id, conversation_id, root_message_id, title, objective) VALUES ('T-1', 2845, 1, 'x', 'Done when: x works')")
    c.execute('INSERT INTO hb_task_requests(request_id, task_id) VALUES (5, ?)', ('T-1',))
    c.execute("INSERT INTO hb_peer_work VALUES (5, 'apex', ?, 'x', 0)", (state,))
    base = [('dispatch', {}), ('progress', {'stage': 'Attached agent picked up the request'}), ('progress', {'stage': 'APEX thinking - round 1'})]
    for n, (kind, p) in enumerate(base + events + [('progress', {'stage': 'Agent answer saved and read back in main chat'})]):
        c.execute('INSERT INTO hb_task_events(task_id, agent, kind, request_id, payload, created_at) VALUES (?,?,?,?,?,?)',
                  ('T-1', 'apex', kind, 5, json.dumps(p), 1000 + n))
    return hb_lights.turn(c, request_id=5)


def _does(lights):
    return {l['key']: l['state'] for l in lights['does']}


def test_does_execute_needs_an_action_proved_by_its_own_check():
    patch = ('tool_result', {'tool': 'propose_patch', 'status': 'succeeded'})
    assert _does(_db([patch]))['execute'] == 'warn'                                        # acted, not proved
    assert _does(_db([patch, ('test_result', {'alm_run_status': 'pass'})]))['execute'] == 'on'
    assert _does(_db([patch, ('test_result', {'alm_run_status': 'fail'})]))['execute'] == 'bad'
    assert _does(_db([('tool_result', {'tool': 'read_file', 'status': 'succeeded'})]))['execute'] == 'warn'   # only reads


def test_turn_group_is_claude_codes_three_and_does_dream_follow():
    lights = _db([('tool_result', {'tool': 'read_file', 'status': 'succeeded'})])
    assert [l['word'] for l in lights['turn']] == ['queue started', 'inference', 'continuity']
    assert [l['word'] for l in lights['does']] == ['Do', 'Operate', 'Execute', 'Sustain']
    assert [l['letter'] for l in lights['dream']] == list('DREAM')
    assert lights['does'][0]['law'] == 'Do - know the goal and the done criteria' and lights['dream'][4]['law'] == 'Motivation - finish'


def test_the_page_shows_three_groups_and_the_meaning_on_hover():

    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    lights = _db([('tool_result', {'tool': 'read_file', 'status': 'succeeded'})])
    js = ROOT / 'frontend/static/js/hb-live.js'
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(js))}); process.stdout.write(R.renderLights({json.dumps(lights)}))"],
                         capture_output=True, text=True, timeout=20).stdout
    for word in ('▶ queue started', '✦ inference', '∞ continuity', '>DOES<', '>Do<', '>Operate<', '>Execute<', '>Sustain<', '>DREAM<',
                 'Execute - one bounded action at a time, proved by its own check · now: No action yet, only reads'):
        assert word in out, word
    assert 'LAW' not in out
    assert out.index('queue started') < out.index('>DOES<') < out.index('>DREAM<')
