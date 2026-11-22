"""Practice 266: no automatic approval; JD is asked with proof."""
import inspect
import sqlite3

from core import hb_plan_workflow, hb_task_manager as tm, hb_apex_swap


def test_auto_accept_is_off_for_everything():
    assert hb_plan_workflow.auto_accept_for(None, {'task_id': 'T-1', 'step_id': 'S-1'}) is False


def test_the_approval_question_carries_proof():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT)')
    c.execute("INSERT INTO hb_task_events(task_id,kind,payload) VALUES ('T-1','mutation','{\"output\": \"Approved patch: core/hb_live.py\"}')")
    c.execute("INSERT INTO hb_task_events(task_id,kind,payload) VALUES ('T-1','test_result','{\"verdict\": \"PASS: 3 passed\", \"alm_run_id\": \"r1\", \"status\": \"passed\"}')")
    assert tm.proof(c, {'task_id': 'T-1'}) == 'Changed: core/hb_live.py. Check: PASS: 3 passed (run r1).'
    assert '{proof(conn,task)} Approve it?' in inspect.getsource(tm.tick)


def test_swift_gets_twenty_rounds():
    assert hb_apex_swap.ROUNDS_BY_MODEL['swift-qwen3.8-27b'] == 20
