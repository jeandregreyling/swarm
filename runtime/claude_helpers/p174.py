"""Prepare Practice 174: running out of tool calls ends the turn with APEX's best answer, not an error."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
T = 'core/apex_tools.py'
edits = [{'path': T, 'old': '''        if (set(payload) not in ({"tool_calls"}, {"tool_calls", "answer"})
                or payload.get("answer") or not isinstance(calls, list) or not calls
                or len(calls) + len(receipts) > MAX_CALLS):
            raise RuntimeError("Invalid or excessive APEX tool calls")
''', 'new': '''        well_formed = (set(payload) in ({"tool_calls"}, {"tool_calls", "answer"}) and not payload.get("answer")
                       and isinstance(calls, list) and bool(calls))
        if well_formed and len(calls) + len(receipts) > MAX_CALLS:
            # Practice 174 (overnight suite 20 Nov 2026, on ROCm): STP2, tax thresholds and retro each had a good answer that a coverage
            # or read check sent back for more notes; APEX then asked for more reads than the turn's MAX_CALLS and the turn ended with
            # "Invalid or excessive APEX tool calls" - no answer at all. Well-formed calls past the budget are trimmed to what is left;
            # with nothing left the turn ends like a turn out of rounds (handoff: APEX's last real answer, else HB's research digest).
            room = MAX_CALLS - len(receipts)
            if room <= 0:
                return handoff(f"APEX used all {MAX_CALLS} tool calls this turn")
            calls = payload["tool_calls"] = calls[:room]
        if not well_formed or len(calls) + len(receipts) > MAX_CALLS:
            raise RuntimeError("Invalid or excessive APEX tool calls")
'''}]

test = '''"""Practice 174: a turn that runs out of tool calls delivers APEX's best answer instead of an error."""
import json

import pytest

import core.apex_tools as t
from core.apex_tools import MAX_CALLS, ReadOnlyRepository, run_apex_tools

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
L = 1 << 40
SEARCH = {'status': 'found', 'matches': ['SAP Note 3793457: 3793457 - Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements | x',
                                         'SAP Note 3808818: 3808818 - PDS Phase 2.1: MCB check extended | y',
                                         'SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super | z'],
          'items': [{'document_id': L + 6655, 'source_ref': 'sap://note/3793457'}, {'document_id': L + 6659, 'source_ref': 'sap://note/3808818'},
                    {'document_id': L + 7004, 'source_ref': 'sap://note/3713786'}]}
EXTRA = [L + 100 + i for i in range(10)] + [L + 500]
SEARCH['matches'] += [f'SAP Note 38000{i:02d}: 38000{i:02d} - MCB related change {i} [document_id {d}] | w' for i, d in enumerate(EXTRA)]
SEARCH['items'] += [{'document_id': d, 'source_ref': f'sap://note/38000{i:02d}'} for i, d in enumerate(EXTRA)]
FIRST = ('SAP Note 3793457 extends the maximum contribution base check from SG funds to non-SG funds that have Apply MCB ticked, and '
         'it adds wage type /XQE for the excess qualifying earnings above the ceiling.\\nSAP Note 3808818 extends the same check to '
         'concurrent employment payrolls and to the non-enhanced private sector super solution.\\nSAP Note 3713786 provides the '
         'legislative background for paying super guarantee on payday from July 2026.\\nThe cap applies per payroll period.')


def _reads(ids):
    return json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': i}} for i in ids], 'answer': ''})


def _turn(tmp_path, monkeypatch, turns):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    reads = []

    def model(_n, msgs):
        return turns.pop(0), 1

    def studio(name, args):
        if name == 'knowledge_search':
            return SEARCH
        reads.append(args['document_id'])
        return {'status': 'found', 'title': 'SAP Note x', 'content': 'text'}
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=studio)
    return answer, reads


def test_out_of_tool_calls_keeps_the_last_real_answer(tmp_path, monkeypatch):
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'Maximum Contribution Base payday super'}}], 'answer': ''}),
             _reads([L + 6655, L + 6659]),
             json.dumps({'tool_calls': [], 'answer': FIRST}),           # cites 3713786 unread: the read check sends it back
             _reads([L + 7004] + [L + 100 + i for i in range(10)]),     # 11 more reads: only the budget left is run
             _reads([L + 500])]                                         # nothing left: the turn ends with the kept answer
    answer, reads = _turn(tmp_path, monkeypatch, turns)
    assert len(reads) == MAX_CALLS - 2 and reads[2] == L + 7004
    assert 'SAP Note 3793457 extends the maximum contribution base' in answer and "APEX's last answer" in answer


def test_malformed_tool_calls_still_fail(tmp_path, monkeypatch):
    turns = [json.dumps({'tool_calls': 'knowledge_read', 'answer': ''})]
    with pytest.raises(RuntimeError, match='Invalid or excessive'):
        _turn(tmp_path, monkeypatch, turns)
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Overnight suite 20 Nov (ROCm): STP2, tax thresholds and retro had good answers that a check sent back for more "
                            "notes; APEX then asked for more reads than MAX_CALLS and the turn raised 'Invalid or excessive APEX tool calls' - "
                            "JD would get no answer. core/apex_tools.run_apex_tools: well-formed calls past the budget are trimmed; with no "
                            "budget left the turn ends via handoff (APEX's last real answer with HB's note, else the research digest). "
                            "Malformed calls still fail."),
                 edits=edits, new_files={'tests/test_practice_174_out_of_tool_calls.py': test},
                 test={'tests': ['tests/test_practice_174_out_of_tool_calls.py', 'tests/test_practice_155_keep_the_answer.py',
                                 'tests/test_practice_143_reasked_questions.py', 'tests/test_practice_154_rounds_and_digest.py',
                                 'tests/test_apex_grounding.py'], 'keyword': ''}, run=run)
print(out['verified'])
