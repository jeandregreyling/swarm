"""Practice 149 (owner 17 Nov 2026): the STP2 answer still left out 3713787, 3749998 and 3735245 after the coverage retry, and APEX
read every note with focus "excerpt". HB now appends the on-topic notes still missing, and replaces a focus unrelated to the question."""
import json

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'
OUT = json.dumps({'matches': [
    'SAP Note 3660828: [document_id 1099511645046] 3660828 - STP2: Performance improvements for CE | The CE report is slow with many employees.',
    'SAP Note 3713787: [document_id 1099511634890] 3713787 - STP2 Reporting Changes for Payday Super | Payday Super legislation from 1 July 2026.',
    'SAP Note 3735245: [document_id 1099511634207] 3735245 - STP2 Concurrent Employment Report Picks Payment Date from Terminated Assignment | x']})


def test_practice_149_appendix_lists_what_is_still_missing():
    rec = [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'STP2'}, 'output': OUT}]
    a = t.coverage_appendix(Q, 'SAP Note 3660828 improves the CE report performance.', rec)
    assert '- SAP Note 3713787: STP2 Reporting Changes for Payday Super - Payday Super legislation from 1 July 2026.' in a
    assert '3735245' in a and '3660828' not in a


def test_practice_149_answer_gets_the_appendix_after_the_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    part = ('SAP Note 3660828: the STP2 concurrent employment report was slow for large employee sets; the note changes the code '
            'so that the report runs faster for many employees.')
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'STP2'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'Single Touch Payroll Phase 2'}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': 1099511645046}},
                                        {'name': 'knowledge_read', 'arguments': {'document_id': 1099511634890}}], 'answer': ''})] + \
            [json.dumps({'tool_calls': [], 'answer': part})] * 5

    def studio(name, args):
        if name == 'knowledge_search':
            return json.loads(OUT)
        return {'status': 'found', 'title': 'SAP Note 3660828: x', 'content': 'y'}
    answer, _, _ = run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None,
                                  ReadOnlyRepository(tmp_path), studio_handler=studio)
    assert '**Also on this topic**' in answer and '3735245' in answer


def test_practice_149_unrelated_focus_is_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    seen = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'STP2'}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': 1099511645046, 'focus': 'excerpt'}}], 'answer': ''})] + \
            [json.dumps({'tool_calls': [], 'answer': 'done'})] * 6

    def studio(name, args):
        seen.append((name, dict(args)))
        return json.loads(OUT) if name == 'knowledge_search' else {'status': 'found', 'title': 'x', 'content': 'y'}
    run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None,
                   ReadOnlyRepository(tmp_path), studio_handler=studio)
    reads = [a for n, a in seen if n == 'knowledge_read']
    assert reads and reads[0]['focus'] != 'excerpt' and 'STP' in reads[0]['focus']
