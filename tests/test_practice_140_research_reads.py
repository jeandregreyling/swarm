"""Practice 140 (owner 17 Nov 2026): asked what the SAP notes say about the MCB cap, what it means and how it is paid, APEX searched four
times, read no note, invented the meaning and the payment ("per payroll period", "a single payment per payroll run") and told JD to "request
the document via the Knowledge Centre". HB now sends such an answer back once to read the best 2-3 notes in one round."""
import json

import core.apex_tools as t
from core import hb_learning
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
L = 1 << 40
SEARCH = {'status': 'found', 'matches': ['SAP Note 3793457: 3793457 - Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements | x',
                                         'SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super | y',
                                         'SAP Note 3749754: 3749754 - Payday Super: MCB flag not updated in V_T5QSF | z',
                                         'SAP Note 3808818: 3808818 - PDS Phase 2.1: MCB check extended | w'],
          'items': [{'document_id': L + 6655, 'source_ref': 'sap://note/3793457'}, {'document_id': L + 7004, 'source_ref': 'sap://note/3713786'},
                    {'document_id': L + 6637, 'source_ref': 'sap://note/3749754'}, {'document_id': L + 6659, 'source_ref': 'sap://note/3808818'}]}


def rec(tool, args, out):
    return {'tool': tool, 'status': 'succeeded', 'arguments': args, 'output': json.dumps(out)}


def test_practice_140_owner_sent_to_fetch():
    assert t.sends_owner_to_fetch('If you need the full text of any note, request the document via the Knowledge Centre.')
    assert not t.sends_owner_to_fetch('SAP Note 3713786 sets the annual cap at 270,830 AUD.')


def test_practice_140_which_notes_to_read():
    r = [rec('knowledge_search', {'query': 'MCB cap'}, SEARCH)]
    assert t.notes_to_read('See 3713786 and 3808818.', r) == [('3713786', L + 7004), ('3808818', L + 6659), ('3793457', L + 6655)]
    r.append(rec('knowledge_read', {'document_id': L + 7004}, {'status': 'found', 'title': 'SAP Note 3713786: x'}))
    assert ('3713786', L + 7004) not in t.notes_to_read('See 3713786.', r)


def test_practice_140_method_says_always_read():
    m = hb_learning.research_method()
    assert 'always knowledge_read the 2-3 most relevant notes' in m and 'never ask the owner to fetch' in m


def test_practice_140_an_answer_without_reads_goes_back(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    seen, reads = [], []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'Maximum Contribution Base payday super'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': 'Notes 3793457, 3713786, 3749754 and 3808818 cover the MCB. It is paid per payroll run. '
                                                     'If you need the full text, request the document via the Knowledge Centre.'})]

    def model(_name, msgs):
        seen.append(str(msgs[-1]['content']))
        if turns:
            return turns.pop(0), 1
        if not reads:
            return json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004}},
                                              {'name': 'knowledge_read', 'arguments': {'document_id': L + 6655}}], 'answer': ''}), 1
        return json.dumps({'tool_calls': [], 'answer': ('SAP Note 3713786: from 1 July 2026 the MCB is an annual cap of 270,830 AUD on qualifying '
                                                        'earnings; above it the employer may stop paying minimum SG.\nSAP Note 3793457: earnings '
                                                        'above the ceiling go to wage type /XQE; Apply MCB extends the check to non-SG funds.\n'
                                                        'SAP Note 3749754: the Apply MCB flag was not saved in V_T5QSF.\nSAP Note 3808818: the '
                                                        'check is extended to concurrent employment, cumulated per person per ABN.')}), 1

    def studio(name, args):
        if name == 'knowledge_search':
            return SEARCH
        if name == 'knowledge_read':
            reads.append(args['document_id'])
            return {'status': 'found', 'title': 'SAP Note x', 'content': 'text'}
        raise AssertionError(name)
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=studio)
    back = [s for s in seen if s.startswith('BACKEND READ CHECK')]
    assert back and 'You read no note' in back[0] and 'HB holds it' in back[0] and str(L + 7004) in back[0]
    assert reads and '270,830' in answer
