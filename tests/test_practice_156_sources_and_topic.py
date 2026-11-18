"""Practice 156 (owner 18 Nov 2026): asked how /001 and /002 work, the 27B searched with 'superannuation' (from the earlier MCB talk),
read nothing and explained the valuation bases as super wage types. A search topic the question never named now goes back once, and the
method says to say first when the notes do not cover the question."""
import json

import core.apex_tools as t
from core import hb_learning
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'tell be how the wage types /001 and /002 work? How to they get their values? What are they for?'
QM = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'


def rec(*queries):
    return [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': q}, 'output': '{}'} for q in queries]


def test_practice_156_imported_topic():
    assert t.imported_topic(Q, rec('wage type /001 /002 superannuation', '/001 /002 wage type Australian payroll',
                                   'wage type /001 superannuation contribution', 'wage type /002 superannuation earnings')) == ['superannuation']
    assert t.imported_topic(QM, rec('MCB cap SAP note', 'Maximum Contribution Base payday super')) == []
    assert t.imported_topic(Q, rec('wage type /001 valuation basis')) == []


def test_practice_156_imported_topic_goes_back(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    seen = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'wage type /001 superannuation'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'wage type /002 superannuation earnings'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': '/001 is super earnings.'})] + [json.dumps({'tool_calls': [], 'answer': 'done'})] * 6

    def model(_n, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1
    run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                   studio_handler=lambda name, args: {'status': 'found', 'matches': []})
    back = [s for s in seen if s.startswith('BACKEND TOPIC CHECK')]
    assert back and "'superannuation'" in back[0]


def test_practice_156_method():
    assert 'say so in your FIRST line' in hb_learning.research_method()


def test_practice_156_wage_type_questions_are_research():
    assert t.research_question(Q)
    assert t.research_question('What does infotype 0008 do?')
    assert not t.research_question('Fix the failing test in core/hb_rename.py')
