"""Practice 138 (owner 17 Nov 2026): "the links are there but the message about what is inside each one or how it relates to the question
is missing". APEX read five notes one per round, ran out of rounds and never answered; JD saw only "Saved unfinished work in Studio".
The research method now says to answer from the search summaries and read at most 2-3 notes in one round, and a research turn that
runs out still answers with what it found."""
import json

import core.apex_tools as t
from core import hb_learning
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'
SEARCH = {'status': 'found', 'matches': ['SAP Note 3660828: 3660828 - STP2: Performance improvements for CE | The CE report is slow.',
                                         'SAP Note 3713941: 3713941 - STP2 : Deletion of Simulation Data | Simulation data cannot be deleted.'],
          'families': [{'component': 'PY-AU-STP', 'notes': ['SAP Note 3700339: RPUSTOQ0 - New option to exclude override entries']}]}


def test_practice_138_method_says_answer_from_summaries_and_read_in_one_round():
    m = hb_learning.research_method()
    assert "after ' | '" in m and 'ALL in one round' in m and 'how it bears on the question' in m


def test_practice_138_digest_lists_what_was_found():
    r = [{'tool': 'knowledge_search', 'status': 'succeeded', 'output': json.dumps(SEARCH)}]
    d = t.research_digest(r)
    assert '- SAP Note 3660828: STP2: Performance improvements for CE - The CE report is slow.' in d
    assert '- SAP Note 3700339: RPUSTOQ0 - New option to exclude override entries' in d and 'go on' in d
    assert t.research_digest([]) == ''


def test_practice_138_a_research_turn_that_runs_out_still_answers(tmp_path, monkeypatch):
    reads = iter(range(1, 50))

    def model(_name, msgs):
        if not any('knowledge_search' in str(m.get('content')) for m in msgs[1:]):
            return json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'STP2'}}], 'answer': ''}), 1
        return json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': next(reads), 'offset': 0}}],
                           'answer': ''}), 1

    def studio(name, args):
        if name == 'knowledge_search':
            return SEARCH
        if name == 'knowledge_read':
            return {'status': 'found', 'title': f"SAP Note 36{args['document_id']:05d}: 36{args['document_id']:05d} - STP2 note", 'content': 'x'}
        raise AssertionError('no Studio handoff for a research question: ' + name)
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=studio)
    assert answer.startswith('APEX used all its tool rounds') and 'The CE report is slow.' in answer
