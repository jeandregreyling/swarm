"""Practice 128 (owner 17 Nov 2026): APEX's second STP2 answer ran one search (the method asks for two wordings), called SAP Note 3708034
"truncated" and said nothing covered 3713787 - both in the Knowledge Centre - and the top search hit was JD's own question (its Studio record).
HB now sends such an answer back once, and Studio records no longer crowd out real notes."""
import json
import sqlite3

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'


def test_practice_128_what_counts_as_a_research_question():
    assert t.research_question(Q)
    assert not t.research_question('Fix the STP2 report in core/stp.py')
    assert not t.research_question('{"task_type": "hb_managed_continuation", "instruction": "research"}')


def test_practice_128_notes_called_missing_that_the_kc_holds(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, source_ref TEXT)')
    db.execute("INSERT INTO knowledge_sources(source_ref) VALUES ('sap://note/3708034')")

    class Keep:
        def __enter__(self): return db
        def __exit__(self, *a): return False
        def close(self): pass
        def execute(self, *a): return db.execute(*a)
    import utils.db._connection as cm
    monkeypatch.setattr(cm, 'get_connection', lambda: Keep())
    answer = ('3660828 fixes the CE report.\nNote 3708034 is truncated in the search results; request it via /notes add 3708034. '
              'Note 3999999 was not found.')
    assert t.kc_notes_claimed_missing(answer) == ['3708034']


def test_practice_128_one_search_is_sent_back_for_a_second(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    turns, seen = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'STP2'}}], 'answer': ''}),
                   json.dumps({'tool_calls': [], 'answer': 'Notes 3660828 and 3710504 cover STP2.'})] + \
                  [json.dumps({'tool_calls': [], 'answer': 'Notes 3660828, 3710504 and 3708034 cover STP2.'})] * 3, []

    def model(_name, msgs):
        seen.append(msgs[-1]['content'])
        return turns.pop(0), 1
    run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                   studio_handler=lambda name, args: {'status': 'found', 'items': []})
    assert any(str(s).startswith('BACKEND RESEARCH CHECK') for s in seen)


def test_practice_128_studio_records_are_hb_records_in_search():
    import core.apex_knowledge as k
    assert "LIKE 'studio://%'" in open(k.__file__).read()
