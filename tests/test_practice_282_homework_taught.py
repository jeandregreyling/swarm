"""Practice 282 (JD 22 Nov: why "the homework models did not deliver the same result" as Claude Code, and why they "have not been corrected
and taught"): homework now gets the chunk rules and two worked examples, HB judges its PLAN (vague steps, invented files), tells it next time
why its last card was rejected, and the chunker uses a homework plan only when HB judged it good."""
import json

from core import hb_chunks, hb_homework as hw

FACTS = {'files': [{'path': 'core/hb_live.py'}, {'path': 'frontend/static/js/hb-live.js'}], 'done_when': ['tests/test_x.py passes']}


def _card(plan):
    return {'goal': 'Show the chunk on each card', 'check': 'python -m pytest tests/test_x.py passes', 'plan': plan, 'scope_in': ['the Live cards'], 'design': ['renderActive in frontend/static/js/hb-live.js'],   # Practice 284
            'files': ['core/hb_live.py'], 'questions': [], 'doer': 'apex', 'importance': 3, 'why': 'x'}


def test_vague_or_invented_plan_steps_are_not_ready():
    ready, why = hw.judge(_card(['Update hb-live.js to include the necessary API endpoints.', 'Ensure that the tests pass.']), FACTS)
    assert not ready and any('vague' in w for w in why)
    ready, why = hw.judge(_card(['add a chunk line in core/hb_boost_map.py', 'run tests/test_x.py']), FACTS)
    assert not ready and any('core/hb_boost_map.py' in w and 'does not exist' in w for w in why)


def test_a_concrete_plan_is_ready():
    ready, why = hw.judge(_card(['run tests/test_x.py and read the first failure',
                                'in frontend/static/js/hb-live.js add the chunk line to renderActive cards',
                                'run tests/test_x.py again until it passes']), FACTS)
    assert ready, why


def test_the_prompt_teaches_chunks_with_examples_and_last_rejection():
    msgs = hw.prompt({'title': 't', 'objective': 'o'}, FACTS, rejected=['plan step 1 is vague: "Ensure that the tests pass."'])
    system, user = msgs[0]['content'], json.loads(msgs[1]['content'])
    assert 'ONE action' in system and 'GOOD plan' in system and 'BAD plan' in system and 'never invent' in system
    assert user['your_last_card_was_rejected_because'] == ['plan step 1 is vague: "Ensure that the tests pass."']


def test_chunker_ignores_a_homework_plan_hb_rejected(monkeypatch):
    import core.hb_homework as h
    monkeypatch.setattr(h, 'latest', lambda conn, task: {'plan': ['a step one', 'a step two'], 'ready': False})
    assert hb_chunks._parts(None, {'task_id': 'T-1'}, 'Make it nice.') == []
    monkeypatch.setattr(h, 'latest', lambda conn, task: {'plan': ['run tests/a.py', 'fix core/a.py'], 'ready': True, 'not_ready': []})
    assert hb_chunks._parts(None, {'task_id': 'T-1'}, 'Make it nice.') == ['run tests/a.py', 'fix core/a.py']
