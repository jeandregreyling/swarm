"""Practice 130 (owner 17 Nov 2026): "it needs to learn how to do research properly". APEX's STP2 answer listed 6 of 13 notes: a search
result was ~12,100 characters but APEX's tool output stops at 8,000, so four STP2 notes never reached it; its "second" search used the
same words; and it said "all relevant notes are present". Searches now fit with every title first, only a clearly different wording
counts as a second search, and an answer that leaves out a topic note the searches returned goes back once."""
import json

import core.apex_tools as t
from core import apex_knowledge as k
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'
NOTES = [('3660828', 'STP2: Performance improvements for CE'), ('3643537', 'STP2: GMOA, GTPR, GTPA cumulation wage types'),
         ('3671186', 'Error in STP-2 Australia Tax Data Upload Utility Report'), ('3713786', 'Phase 1 Payroll Changes for Payday Super'),
         ('3706319', 'CALC: Illness absences reporting in Giorno'), ('3832817', 'DSN: fix for COSTP retroactive change')]


def _result(query):
    return {'status': 'found', 'query': query, 'items': [{'title': f'SAP Note {n}: {n} - {title}', 'excerpt': 'x' * 2000} for n, title in NOTES]}


def _receipt(query):
    return {'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': query}, 'output': json.dumps(_result(query))[:8000]}


def test_practice_130_a_search_fits_and_lists_every_title_first():
    r = k._fit({**_result('STP2'), 'items': _result('STP2')['items'] * 2, 'notice': 'n'})
    assert len(json.dumps(r)) <= k.FIT_CHARS and len(r['matches']) == 12
    assert list(r).index('matches') < list(r).index('items')


def test_practice_130_only_a_different_wording_is_a_second_search():
    same = [_receipt('STP Phase 2 Australian payroll SAP Note'), _receipt('STP Phase 2 Australian payroll'), _receipt('SAP Note 3713787')]
    assert t.distinct_topic_searches(same) == 1
    assert t.distinct_topic_searches(same + [_receipt('STP2')]) == 2


def test_practice_130_topic_notes_left_out_of_the_answer():
    left = t.notes_left_out(Q, 'SAP Note 3660828 improves CE performance.', [_receipt('STP2')])
    assert [x.split()[0] for x in left] == ['3643537', '3671186']      # not Payday Super phase 1, Italian CALC or COSTP


def test_practice_130_an_answer_that_leaves_notes_out_goes_back(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    turns, seen = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'STP2'}}], 'answer': ''}),
                   json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'Single Touch Payroll Phase 2'}}], 'answer': ''}),
                   json.dumps({'tool_calls': [], 'answer': 'Note 3660828 covers STP2. Nothing is missing.'})] + \
                  [json.dumps({'tool_calls': [], 'answer': 'Notes 3660828, 3643537 and 3671186 cover STP2.'})] * 3, []

    def model(_name, msgs):
        seen.append(msgs[-1]['content'])
        return turns.pop(0), 1
    run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                   studio_handler=lambda name, args: _result(args.get('query')))
    back = [s for s in seen if str(s).startswith('BACKEND COVERAGE CHECK')]
    assert back and '3643537' in back[0] and '3671186' in back[0] and not any(str(s).startswith('BACKEND RESEARCH CHECK') for s in seen)
