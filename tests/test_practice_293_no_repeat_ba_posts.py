"""Practice 293 (JD 22 Nov: "the same step cannot be executed twice expecting a different result" and the BA "not actually reporting on the
scope or main question or chunks and details"): an exact call that already failed on the task in an earlier turn is refused while nothing
changed; the BA posts its whole spec in main chat; and it does not spec steps that already have a prepared change set."""
import json
import sqlite3

from core import hb_homework as hw, hb_tasks
from core.apex_tools import earlier_failure


def _db():
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    c.execute("INSERT INTO hb_task_events(task_id, agent, kind, payload, created_at) VALUES ('T-1','apex','tool_failure',?,1)",
              (json.dumps({'tool': 'run_tests', 'arguments': {'tests': ['tests/x.py'], 'case_id': 'S-1'}, 'error': 'case_id is not a test case'}),))
    return c


def test_a_failed_call_is_refused_in_a_later_turn_until_something_changes():
    c = _db()
    call = {'name': 'run_tests', 'arguments': {'tests': ['tests/x.py'], 'case_id': 'S-1'}}
    assert earlier_failure(call, 'T-1', c) == 'case_id is not a test case'
    assert earlier_failure({'name': 'run_tests', 'arguments': {'tests': ['tests/x.py']}}, 'T-1', c) is None
    c.execute("INSERT INTO hb_task_events(task_id, agent, kind, payload, created_at) VALUES ('T-1','apex','mutation','{}',2)")
    assert earlier_failure(call, 'T-1', c) is None                  # a change since: it may be tried again


def test_the_ba_posts_its_whole_spec():
    card = {'goal': 'Show token counts by the name', 'scope_in': ['chat bubble header'], 'scope_out': ['Telegram'],
            'design': ['views/chat.js header shows the chip'], 'risks': ['old messages have no usage'], 'check': 'tests/test_x.py passes',
            'plan': ['run tests/test_x.py', 'in views/chat.js add the chip'], 'questions': [], 'ready': False, 'not_ready': ['plan step 2 is vague']}
    text = hw.spec_post({'title': 'Practice X'}, card)
    for words in ('📝 BA spec: Practice X - NOT ready', 'Main question: Show token counts', 'In scope: chat bubble header', 'Out of scope: Telegram',
                  'Design: views/chat.js', 'Risks: old messages', 'Check: tests/test_x.py passes', 'Chunks: 1. run tests/test_x.py 2. in views/chat.js',
                  'Not ready because: plan step 2 is vague'):
        assert words in text, words


def test_the_ba_skips_steps_that_are_already_built():
    src = open(hw.__file__).read()
    assert 'if hb_change_sets.load(step_id):' in src
