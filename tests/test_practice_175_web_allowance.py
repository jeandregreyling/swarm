"""Practice 175: a turn that used its knowledge budget can still search the web when HB's online check asks for it."""
import json

import core.apex_tools as t
import core.hb_web_research as w
from core.apex_tools import MAX_CALLS, ReadOnlyRepository, run_apex_tools

Q = 'tell be how the wage types /001 and /002 work? How to they get their values? What are they for?'
RESULT = {'provider': 'serper', 'query': 'SAP valuation basis /001 /002',
          'sources': ['https://help.sap.com/docs/HR/x/valuation.html', 'https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636'],
          'text': ('- Valuation bases, valuation of wage types: Valuation bases are rates used to value other wage types.\n'
                   '  Source: https://help.sap.com/docs/HR/x/valuation.html\n'
                   '- Solved: Valuation Basis /001 & /002: calculated by adding the basic pay in calculation rule X010.\n'
                   '  Source: https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636\n')}


def _searches(words):
    return json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': ('/001 /002 ' + x)}} for x in words], 'answer': ''})


def test_web_search_still_runs_after_the_knowledge_budget_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    monkeypatch.setattr(w, 'capture_later', lambda result: None)
    seen, webs = [], []
    turns = [_searches(['valuation basis', 'hourly rate', 'basic pay', 'rule X010', 'technical wage type', 'payroll value']),
             _searches(['daily rate', 'infotype 0008', 'time wage types', 'average rate', 'T512W valuation', 'schema PRIMA']),
             json.dumps({'tool_calls': [], 'answer': 'Our notes do not define /001 and /002. General knowledge: they are basic pay.'}),
             json.dumps({'tool_calls': [{'name': 'web_search', 'arguments': {'query': 'SAP valuation basis /001 /002 help.sap.com', 'provider': 'serper'}},
                                        {'name': 'web_search', 'arguments': {'query': 'SAP /001 /002 valuation basis X010', 'provider': 'serper'}}],
                         'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': ('Our notes do not define them; public SAP pages do: /001 and /002 are valuation bases, '
                                                      'rates from basic pay (rule X010) used to value time wage types. '
                                                      'https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636')})] + \
            [json.dumps({'tool_calls': [], 'answer': 'done'})] * 4

    def model(_n, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1

    def web(args):
        webs.append(args['query'])
        return RESULT
    answer, _, receipts = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                         studio_handler=lambda name, args: {'status': 'found', 'matches': []}, web_handler=web)
    assert sum(1 for r in receipts if r['tool'] == 'knowledge_search') == MAX_CALLS
    assert any(s.startswith('BACKEND ONLINE CHECK') for s in seen)
    assert len(webs) == 2 and 'valuation bases' in answer
