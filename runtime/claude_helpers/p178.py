"""Prepare Practice 178: a final answer does not talk about drafts the owner never saw ("Correction to my earlier answer")."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
T = 'core/apex_tools.py'
helper = '''# Practice 178 (suite 20 Nov 2026, /001 and /002): the delivered answer opened "Correction to my earlier answer - /001 and /002 are not
# gross pay and net pay". JD never saw that earlier answer: HB's online check had sent the draft back. When a draft was sent back this
# turn, a leading phrase about correcting an earlier/previous answer is removed; the rest of the sentence stays.
_RETRY_TALK = re.compile(r"^\\s*(?:\\*\\*)?(?:correction(?: to| of)? my (?:earlier|previous|first|last) answer|correcting my (?:earlier|previous|first|last) "
                         r"answer|to correct my (?:earlier|previous|first|last) answer|(?:i was wrong|my (?:earlier|previous|first) answer was wrong)"
                         r"(?: earlier| before)?)\\s*(?:[-\\u2013\\u2014:,.]\\s*)?(?:\\*\\*)?\\s*(?:[-\\u2013\\u2014:,.]\\s*)?", re.I)


def drop_retry_talk(answer) -> str:
    text = str(answer or '')
    new = _RETRY_TALK.sub('', text, count=1)
    if new == text:
        return text
    return new[:1].upper() + new[1:]


def drop_nothing_more(answer) -> str:
'''
edits = [
    {'path': T, 'old': "def drop_nothing_more(answer) -> str:\n", 'new': helper},
    {'path': T, 'old': '''        delivered = _grounded(answer, can_retry, can_fix)
''', 'new': '''        delivered = _grounded(answer, can_retry, can_fix)
        if isinstance(delivered, str) and any(m.get('rejected_answer') for m in working):
            delivered = drop_retry_talk(delivered)        # Practice 178: JD never saw the draft that was sent back
'''},
]

test = '''"""Practice 178: a final answer does not talk about drafts the owner never saw."""
import json

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, drop_retry_talk, run_apex_tools


def test_drop_retry_talk():
    assert drop_retry_talk('Correction to my earlier answer \\u2014 /001 and /002 are **not** gross pay.') == '/001 and /002 are **not** gross pay.'
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
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004}}], 'answer': ''})] + \\
            [json.dumps({'tool_calls': [], 'answer': good})] * 4

    def studio(name, args):
        return search if name == 'knowledge_search' else {'status': 'found', 'title': 'SAP Note 3713786', 'content': 'payday super text'}
    answer, _, _ = run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'What do our SAP notes say about the MCB cap?'}],
                                  lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path), studio_handler=studio)
    assert answer.startswith('SAP Note 3713786: from 1 July 2026') and 'Correction to my earlier answer' not in answer
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Suite 20 Nov: the /001 /002 answer opened \"Correction to my earlier answer - /001 and /002 are not gross pay and net "
                            "pay\" - JD never saw that draft, HB's online check had sent it back. core/apex_tools: drop_retry_talk() removes a "
                            "leading 'correction to my earlier/previous answer' phrase from the delivered answer when a draft was sent back "
                            "this turn."),
                 edits=edits, new_files={'tests/test_practice_178_no_retry_talk.py': test},
                 test={'tests': ['tests/test_practice_178_no_retry_talk.py', 'tests/test_practice_176_see_apex_work.py',
                                 'tests/test_practice_175_web_allowance.py', 'tests/test_practice_174_out_of_tool_calls.py',
                                 'tests/test_practice_155_keep_the_answer.py', 'tests/test_practice_143_reasked_questions.py',
                                 'tests/test_apex_grounding.py'], 'keyword': ''}, run=run)
print(out['verified'])
