"""Prepare Practice 175: web searches have their own allowance, so a turn that used its note budget can still go online."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
T = 'core/apex_tools.py'
edits = [
    {'path': T, 'old': "MAX_CALLS = 12\n", 'new': ("MAX_CALLS = 12\n"
                                                   "MAX_WEB_CALLS = 4     # Practice 175: web_search calls have their own allowance on top of MAX_CALLS\n")},
    {'path': T, 'old': '''        if well_formed and len(calls) + len(receipts) > MAX_CALLS:
            # Practice 174 (overnight suite 20 Nov 2026, on ROCm): STP2, tax thresholds and retro each had a good answer that a coverage
            # or read check sent back for more notes; APEX then asked for more reads than the turn's MAX_CALLS and the turn ended with
            # "Invalid or excessive APEX tool calls" - no answer at all. Well-formed calls past the budget are trimmed to what is left;
            # with nothing left the turn ends like a turn out of rounds (handoff: APEX's last real answer, else HB's research digest).
            room = MAX_CALLS - len(receipts)
            if room <= 0:
                return handoff(f"APEX used all {MAX_CALLS} tool calls this turn")
            calls = payload["tool_calls"] = calls[:room]
        if not well_formed or len(calls) + len(receipts) > MAX_CALLS:
            raise RuntimeError("Invalid or excessive APEX tool calls")''', 'new': '''        # Practice 174 (overnight suite 20 Nov 2026, on ROCm): STP2, tax thresholds and retro each had a good answer that a coverage
        # or read check sent back for more notes; APEX then asked for more reads than the turn's MAX_CALLS and the turn ended with
        # "Invalid or excessive APEX tool calls" - no answer at all. Well-formed calls past the budget are trimmed to what is left;
        # with nothing left the turn ends like a turn out of rounds (handoff: APEX's last real answer, else HB's research digest).
        # Practice 175 (suite rerun 20 Nov 2026): /001 and /002 - ten knowledge calls found nothing, HB's online check rightly asked for
        # web_search, and the two searches did not fit the two calls left, so the turn ended with a list of unrelated notes. Knowledge
        # calls count against MAX_CALLS, web searches against their own MAX_WEB_CALLS.
        used_web = sum(1 for r in receipts if r.get("tool") == "web_search")
        if well_formed:
            room, web_room, kept = MAX_CALLS - (len(receipts) - used_web), MAX_WEB_CALLS - used_web, []
            for call in calls:
                web = isinstance(call, dict) and call.get("name") == "web_search"
                if web and web_room > 0:
                    web_room -= 1
                    kept.append(call)
                elif not web and room > 0:
                    room -= 1
                    kept.append(call)
            if not kept:
                return handoff(f"APEX used all {MAX_CALLS} tool calls this turn")
            calls = payload["tool_calls"] = kept
        if not well_formed or len(calls) + len(receipts) > MAX_CALLS + MAX_WEB_CALLS:
            raise RuntimeError("Invalid or excessive APEX tool calls")'''},
]

test = '''"""Practice 175: a turn that used its knowledge budget can still search the web when HB's online check asks for it."""
import json

import core.apex_tools as t
import core.hb_web_research as w
from core.apex_tools import MAX_CALLS, ReadOnlyRepository, run_apex_tools

Q = 'tell be how the wage types /001 and /002 work? How to they get their values? What are they for?'
RESULT = {'provider': 'serper', 'query': 'SAP valuation basis /001 /002',
          'sources': ['https://help.sap.com/docs/HR/x/valuation.html', 'https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636'],
          'text': ('- Valuation bases, valuation of wage types: Valuation bases are rates used to value other wage types.\\n'
                   '  Source: https://help.sap.com/docs/HR/x/valuation.html\\n'
                   '- Solved: Valuation Basis /001 & /002: calculated by adding the basic pay in calculation rule X010.\\n'
                   '  Source: https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636\\n')}


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
                                                      'https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636')})] + \\
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
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Suite rerun 20 Nov (ROCm): /001 and /002 - ten knowledge calls found nothing on topic, HB's online check rightly "
                            "asked for web_search, and the two searches did not fit the two calls left (Practice 174 trimmed them), so JD got "
                            "a list of unrelated notes. core/apex_tools: web_search calls get their own allowance (MAX_WEB_CALLS = 4) on top of "
                            "MAX_CALLS; knowledge calls are still trimmed at MAX_CALLS."),
                 edits=edits, new_files={'tests/test_practice_175_web_allowance.py': test},
                 test={'tests': ['tests/test_practice_175_web_allowance.py', 'tests/test_practice_174_out_of_tool_calls.py',
                                 'tests/test_practice_157_online_research.py', 'tests/test_practice_155_keep_the_answer.py',
                                 'tests/test_practice_143_reasked_questions.py', 'tests/test_apex_grounding.py'], 'keyword': ''}, run=run)
print(out['verified'])
