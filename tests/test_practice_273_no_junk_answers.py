"""Practice 273 (JD 22 Nov 09:2x: "I asked you to build the fucking icons and link them to DOES and DREAM" and "ensure that apex doesn't
give me more 'fuck you dude' answers"): the icons name their DOES letter, and on HB's own work turns APEX's plan, promise, restated
checklist or a tool's error never reaches JD as an answer - he is sent back once, then HB says plainly that nothing was done."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.apex_tools import NO_WORK_NOTICE, PARROT_NOTICE, no_work, no_work_line, parroted_error

ROOT = Path(__file__).resolve().parents[1]
CONT = '{"task_type": "hb_managed_continuation", "task_id": "T-9413143BF870", "sequence": 2, "instruction": "Continue the task"}'
PLAN = '{"task_type": "hb_managed_plan", "task_id": "T-1", "instruction": "HB workflow, DREAM step 1 (Distinguish): scope this step"}'
PATCH_FAIL = {'tool': 'propose_patch', 'status': 'failed', 'output': 'The patch was rejected because the exact patch text matched 0 locations. '
              'Provide a larger unique context chunk from a fresh raw read. No transaction was created.'}
READ = {'tool': 'read_file', 'status': 'succeeded', 'output': 'x'}


def test_the_three_junk_answers_from_22_14_to_22_18_are_not_work():
    # 21258 promise, 21263 tool error handed to JD, 21266 restated checklist - all on HB continuation turns with no action
    for answer in ('The task is not yet complete. The next step is to run the tests for this change.',
                   'The patch was rejected because the exact patch text matched 0 locations. Provide a larger unique context chunk from a '
                   'fresh raw read. Please provide the larger unique context chunk from a fresh raw read.',
                   "The step S-4A173B424A was found and its status is 'todo'. The plan is to do each item in the checklist."):
        assert no_work(answer, [READ, PATCH_FAIL], CONT), answer


def test_real_work_blockers_jd_turns_and_scoping_turns_pass():
    assert not no_work('Done: patched core/x.py (receipt a1); tests pass.', [{'tool': 'propose_patch', 'status': 'succeeded'}], CONT)
    assert not no_work('Done: 3 passed.', [{'tool': 'run_tests', 'status': 'succeeded'}], CONT)
    assert not no_work('Blocked because propose_patch is denied on this file: owner review pending.', [PATCH_FAIL], CONT)
    assert not no_work('The plan is to add a test.', [READ], 'What is the plan for the UI controls?')   # JD asked: not an HB work turn
    assert not no_work('Done when: the API lists every control. Plan: 1. read 2. patch', [READ], PLAN)   # scoping turns answer with a plan


def test_a_tool_error_handed_to_jd_is_caught_on_any_turn():
    junk = 'Provide a larger unique context chunk from a fresh raw read. No transaction was created.'
    assert parroted_error(junk, [PATCH_FAIL])
    assert not parroted_error('The patch did not fit, so I read lines 40-60 again and patched them (receipt b2).', [PATCH_FAIL])
    assert not parroted_error(junk, [READ])


def test_notices_tell_apex_what_to_do_and_the_fallback_line_is_honest():
    assert 'read_file' in NO_WORK_NOTICE and 'blocked because' in NO_WORK_NOTICE and 'JD asked nothing' in NO_WORK_NOTICE
    assert 'instruction to you' in PARROT_NOTICE
    line = no_work_line([READ, PATCH_FAIL])
    assert line.startswith('⏸ HB DOES check: APEX took no action this turn') and 'propose_patch' in line and 'matched 0 locations' in line
    assert no_work_line([READ]).endswith('HB gives him the next turn.')


def test_the_gate_is_wired_into_apexs_turn():
    src = (ROOT / 'core/apex_tools.py').read_text()
    assert 'no_work(answer, receipts, latest_user)' in src and 'parroted_error(answer, receipts)' in src
    assert 'delivered = no_work_line(receipts)' in src


def test_the_does_icons_name_their_letter():
    """Practice 274 replaced 273's labels: DOES icons show their LAW word (Do, Operate, Execute, Sustain)."""
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    light = lambda key, word, icon: {'key': key, 'letter': word[0], 'word': word, 'icon': icon, 'law': 'x', 'state': 'on', 'why': 'y'}
    lights = {'turn': [light('queue', 'queue started', '▶')], 'does': [light('do', 'Do', 'Do')], 'dream': [light('d', 'Distinguish', 'D')]}
    js = ROOT / 'frontend/static/js/hb-live.js'
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(js))}); process.stdout.write(R.renderLights({json.dumps(lights)}))"],
                         capture_output=True, text=True, timeout=20)
    assert '>Do</span>' in out.stdout and '▶ queue started' in out.stdout and 'DREAM' in out.stdout
