"""Practice 145 (owner 17 Nov 2026, "keep going asking and checking the answer till it's right"): APEX guessed document ids (12345 before
any search; 1099511634790-792 for SAP Note 3749754, real id 1099511634413), read SAP HANA notes and said 3749754 was not in the KC. Every
match line now carries its document_id, the coverage check names it, and a guessed id is refused in a research turn."""
import json

import core.apex_knowledge as k
import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
L = 1 << 40


def test_practice_145_match_lines_carry_the_id():
    r = k._fit({'status': 'found', 'query': 'MCB', 'items': [
        {'document_id': L + 6637, 'title': 'SAP Note 3749754: 3749754 - Payday Super: MCB flag not updated in V_T5QSF', 'summary': 'Flag not saved.',
         'source_ref': 'sap://note/3749754'}]})
    assert r['matches'][0] == f'SAP Note 3749754: [document_id {L + 6637}] 3749754 - Payday Super: MCB flag not updated in V_T5QSF | Flag not saved.'


def test_practice_145_parsers_strip_the_id_and_find_it():
    out = json.dumps({'matches': [f'SAP Note 3749754: [document_id {L + 6637}] 3749754 - Payday Super: MCB flag not updated in V_T5QSF | Flag not saved.']})
    rec = [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'MCB'}, 'output': out}]
    assert t._search_results(rec)[0][1][0][1].startswith('3749754 - Payday Super')
    assert t.note_ids(rec) == {'3749754': L + 6637}
    left = t.notes_left_out(Q, 'Only 3793457 matters.', rec)
    assert left and f'[document_id {L + 6637}]' in left[0]
    assert '- SAP Note 3749754: Payday Super: MCB flag not updated in V_T5QSF - Flag not saved.' in t.research_digest(rec)


def test_practice_145_a_guessed_id_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    reads = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_read', 'arguments': {'document_id': 12345}}], 'answer': ''})] + \
            [json.dumps({'tool_calls': [], 'answer': 'done'})] * 6

    def studio(name, args):
        if name == 'knowledge_read':
            reads.append(args['document_id'])
            return {'status': 'found', 'title': 'x', 'content': 'y'}
        return {'status': 'found', 'matches': ['SAP Note 3713786: [document_id 1099511634780] 3713786 - Phase 1 | z']}
    _a, _t, receipts = run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None,
                                      ReadOnlyRepository(tmp_path), studio_handler=studio)
    assert 12345 not in reads
    bad = [r for r in receipts if r['tool'] == 'knowledge_read']
    assert bad and bad[0]['status'] == 'failed' and 'GUESS' in str(bad[0].get('output') or bad[0].get('error'))
