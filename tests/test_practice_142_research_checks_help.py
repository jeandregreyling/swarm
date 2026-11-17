"""Practice 142 (owner 17 Nov 2026): on the MCB question APEX searched once, read the four MCB notes and answered; BACKEND RESEARCH
CHECK sent that answer back with STP2 examples and "answer listing every matching note with its number and title", and the delivered answer
was a title list padded with unrelated notes. Reading two or more notes now satisfies the check, its wording follows the question, and a
title list written inline is still a title list."""
import json

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
L = 1 << 40
SEARCH = {'status': 'found', 'matches': ['SAP Note 3793457: 3793457 - Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements | x',
                                         'SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super | y'],
          'items': [{'document_id': L + 6655, 'source_ref': 'sap://note/3793457'}, {'document_id': L + 7004, 'source_ref': 'sap://note/3713786'}]}
GOOD = ('SAP Note 3713786: from 1 July 2026 the MCB is an annual cap of 270,830 AUD on qualifying earnings (/141); once they reach it the '
        'employer may stop paying the minimum SG for that year.\nSAP Note 3793457: earnings above the ceiling go to wage type /XQE, and the '
        'check also covers non-SG funds with Apply MCB ticked in V_T5QSF.')


def test_practice_142_a_researched_answer_is_delivered_as_written(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    seen = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap SAP Note'}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004, 'focus': 'MCB'}},
                                        {'name': 'knowledge_read', 'arguments': {'document_id': L + 6655, 'focus': 'MCB'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': GOOD})] + [json.dumps({'tool_calls': [], 'answer': 'titles only'})] * 3

    def model(_n, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1

    def studio(name, args):
        return SEARCH if name == 'knowledge_search' else {'status': 'found', 'title': 'SAP Note x', 'content': '270,830'}
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=studio)
    assert not [s[:300] for s in seen if s.startswith('BACKEND') and ' CHECK' in s[:40]]
    assert '270,830' in answer and '/XQE' in answer


def test_practice_142_research_check_wording_follows_the_question(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    seen = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': 'The MCB is a cap.'})] + [json.dumps({'tool_calls': [], 'answer': GOOD})] * 4

    def model(_n, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1
    run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                   studio_handler=lambda name, args: SEARCH if name == 'knowledge_search' else {'status': 'found', 'title': 'x', 'content': 'y'})
    back = [s for s in seen if s.startswith('BACKEND RESEARCH CHECK')]
    assert back and "'MCB'" in back[0] and 'STP2' not in back[0] and 'every part of it' in back[0]
    assert 'listing every matching note' not in back[0]


def test_practice_142_an_inline_title_list_is_titles_only():
    r = [{'tool': 'knowledge_search', 'status': 'succeeded', 'output': json.dumps({'matches': [
        'SAP Note 3793457: 3793457 - Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements | x',
        'SAP Note 3808818: 3808818 - PDS Phase 2.1: MCB check extended to Concurrent Employment | y',
        'SAP Note 3749754: 3749754 - Payday Super: MCB flag not updated in V_T5QSF | z']})}]
    inline = ('Matching notes: 1. SAP Note 3793457 - "Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements" '
              '2. SAP Note 3808818 - "PDS Phase 2.1: MCB check extended to Concurrent Employment" 3. SAP Note 3749754 - '
              '"Payday Super: MCB flag not updated in V_T5QSF"')
    assert t.titles_only(inline, r)
    assert not t.titles_only(GOOD, r)
