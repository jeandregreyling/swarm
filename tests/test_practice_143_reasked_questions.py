"""Practice 143 (owner 17 Nov 2026): the fourth MCB answer described 3713786 and 3749754 without reading them and copied the first answer's
invented "what it means" / "how it is paid" from the chat history. Cited notes are now read, and a re-asked question does not carry
APEX's earlier replies to it."""
import json

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, run_apex_tools
from core.chat_continuity import apex_request_history, same_question

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
L = 1 << 40
SEARCH = {'status': 'found', 'matches': ['SAP Note 3793457: 3793457 - Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements | x',
                                         'SAP Note 3808818: 3808818 - PDS Phase 2.1: MCB check extended | y',
                                         'SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super | z'],
          'items': [{'document_id': L + 6655, 'source_ref': 'sap://note/3793457'}, {'document_id': L + 6659, 'source_ref': 'sap://note/3808818'},
                    {'document_id': L + 7004, 'source_ref': 'sap://note/3713786'}]}


def test_practice_143_same_question():
    assert same_question(Q, 'What do thew SAP notes say about the MCB cap, what does it mean and how is it paid?')
    assert not same_question(Q, 'What do our SAP notes say about STP Phase 2 issues in Australian payroll?')
    assert not same_question('go', 'go')


def test_practice_143_earlier_answers_to_the_same_question_are_left_out():
    h = [{'role': 'user', 'content': 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'},
         {'role': 'assistant', 'content': 'single payment per payroll run'},
         {'role': 'assistant', 'content': '[tool:knowledge_search] ...'},
         {'role': 'user', 'content': 'and the auto scroll button is missing'},
         {'role': 'assistant', 'content': 'about the button'},
         {'role': 'user', 'content': Q}]
    r = apex_request_history(h, Q)
    text = json.dumps(r)
    assert 'single payment per payroll run' not in text and 'about the button' in text
    assert r[-1] == {'role': 'user', 'content': Q} and 'left out' in r[-2]['content']
    assert sum(1 for m in r if m['content'] == Q) == 2   # the owner's own earlier message stays


def test_practice_143_cited_but_unread_notes_go_back(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    seen, reads = [], []
    first = ('SAP Note 3793457 extends the maximum contribution base check from SG funds to non-SG funds that have Apply MCB ticked, and '
             'it adds wage type /XQE for the excess qualifying earnings above the ceiling.\nSAP Note 3808818 extends the same check to '
             'concurrent employment payrolls and to the non-enhanced private sector super solution.\nSAP Note 3713786 provides the '
             'legislative background for paying super guarantee on payday from July 2026.\nThe cap applies per payroll period.')
    good = ('SAP Note 3713786: from 1 July 2026 the MCB is an annual cap of 270,830 AUD on qualifying earnings.\nSAP Note 3793457: '
            'excess goes to /XQE.\nSAP Note 3808818: concurrent employment counts per person.')
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'Maximum Contribution Base payday super'}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 6655}},
                                        {'name': 'knowledge_read', 'arguments': {'document_id': L + 6659}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': first}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': good})] + [json.dumps({'tool_calls': [], 'answer': good})] * 3

    def model(_n, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1

    def studio(name, args):
        if name == 'knowledge_search':
            return SEARCH
        reads.append(args['document_id'])
        return {'status': 'found', 'title': 'SAP Note x', 'content': 'text'}
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=studio)
    back = [s for s in seen if s.startswith('BACKEND READ CHECK')]
    assert back and '3713786' in back[0] and 'did not read this turn' in back[0]
    assert L + 7004 in reads and '270,830' in answer
