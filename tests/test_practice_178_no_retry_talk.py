"""Practice 178: a final answer does not talk about drafts the owner never saw."""
import json

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, drop_retry_talk, run_apex_tools


def test_drop_retry_talk():
    assert drop_retry_talk('Correction to my earlier answer \u2014 /001 and /002 are **not** gross pay.') == '/001 and /002 are **not** gross pay.'
    assert drop_retry_talk('**Correction to my previous answer:** they are valuation bases.') == 'They are valuation bases.'
    assert drop_retry_talk('Correcting my earlier answer, the cap is annual.') == 'The cap is annual.'
    same = 'The earlier answer in SAP Note 123 was corrected by SAP.'
    assert drop_retry_talk(same) == same


def test_turn_drops_it_only_after_a_draft_was_sent_back(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    L = 1 << 40
    search = {'status': 'found', 'matches': ['SAP Note 3713786: 3713786 - Payday Super | z'],
              'items': [{'document_id': L + 7004, 'source_ref': 'sap://note/3713786'}]}
    good = 'Correction to my earlier answer - SAP Note 3713786: from 1 July 2026 super is paid on payday; the MCB is an annual cap.'
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'Maximum Contribution Base'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': good}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004}}], 'answer': ''})] + \
            [json.dumps({'tool_calls': [], 'answer': good})] * 4

    def studio(name, args):
        return search if name == 'knowledge_search' else {'status': 'found', 'title': 'SAP Note 3713786', 'content': 'payday super text'}
    answer, _, _ = run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'What do our SAP notes say about the MCB cap?'}],
                                  lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path), studio_handler=studio)
    assert answer.startswith('SAP Note 3713786: from 1 July 2026') and 'Correction to my earlier answer' not in answer
