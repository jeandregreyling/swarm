"""Practice 141 (owner 17 Nov 2026): after Practice 140 APEX read the MCB notes but never said what the cap means or how it is paid -
knowledge_read returned 1,500 characters from offset 0 and SAP Note 3713786 defines the MCB around character 3,000. A research turn's
read now shows the passages that mention the question's words; {document_id} and {document_id, offset: 0} are one read."""
import json

import core.apex_knowledge as k
import core.apex_tools as t
from core import hb_learning
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
L = 1 << 40
NOTE = ('SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super\ncomponent PY-AU | version 8\nSymptom\n\n'
        + '\n\n'.join(f'Filler paragraph {i} about qualifying earnings wage types and evaluation classes.' * 3 for i in range(30))
        + '\n\nMaximum Contribution Base (MCB): From July 1, 2026, the maximum contribution base(MCB) check is changing from Quarterly to an '
          'Annual amount of 270,830 AUD. If your payments of qualifying earnings reach the MCB, you can stop paying the minimum SG.\n\n'
          'MCB only applies to cap QE amounts to calculate the Super Guarantee Contribution.\n\n'
        + '\n\n'.join(f'Tail paragraph {i}.' * 5 for i in range(20)))


def test_practice_141_focus_words_and_passages():
    assert k.focus_words(Q) == ['MCB', 'cap', 'paid']
    p = k.focus_passages(NOTE, 'MCB cap paid')
    assert p.startswith('SAP Note 3713786') and '270,830 AUD' in p and 'stop paying the minimum SG' in p and len(p) <= k.FOCUS_CHARS + 40
    assert 'Filler paragraph 3 ' not in p
    assert k.focus_passages(NOTE, 'nothing-here') == ''


def test_practice_141_read_with_focus(monkeypatch):
    monkeypatch.setattr(k, '_full_text', lambda _d: NOTE)
    plain = {'status': 'found', 'document_id': L + 7004, 'title': 'SAP Note 3713786', 'content': NOTE[:1500], 'next_offset': 1500}
    r = k._focused(dict(plain), L + 7004, 'MCB cap paid')
    assert '270,830' in r['content'] and r['next_offset'] == 1500 and 'offset 1500' in r['focus_note']
    assert k._focused(dict(plain, next_offset=None), L + 7004, 'MCB') ['content'] == NOTE[:1500]


def test_practice_141_read_focus_of_a_question():
    assert t.read_focus(Q).split()[0] == 'MCB' and 'paid' in t.read_focus(Q)


def test_practice_141_method_answers_every_part():
    assert 'Answer EVERY part of the question' in hb_learning.research_method()


def test_practice_141_research_reads_carry_focus_and_repeat_reads_are_one(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    calls = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'Maximum Contribution Base payday super'}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004, 'offset': 0}}], 'answer': ''})] + \
            [json.dumps({'tool_calls': [], 'answer': 'SAP Note 3713786: from 1 July 2026 the MCB is an annual cap of 270,830 AUD on qualifying earnings.'})] * 4

    def studio(name, args):
        calls.append((name, dict(args)))
        if name == 'knowledge_search':
            return {'status': 'found', 'matches': ['SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super | x'],
                    'items': [{'document_id': L + 7004, 'source_ref': 'sap://note/3713786'}]}
        return {'status': 'found', 'title': 'SAP Note 3713786: x', 'content': '270,830'}
    run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None,
                   ReadOnlyRepository(tmp_path), studio_handler=studio)
    reads = [a for n, a in calls if n == 'knowledge_read']
    assert len(reads) == 1 and reads[0]['offset'] == 0 and reads[0]['focus'].startswith('MCB')


def test_practice_141_dispatchers_accept_focus():
    import core.hb_workflow as w
    assert "'focus'" in open(w.__file__).read()
    assert "args.get('focus')" in open('frontend/blueprints/chat.py').read()
