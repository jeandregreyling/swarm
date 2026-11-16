"""Practice 127 (owner 17 Nov 2026): asked "What do our SAP notes say about STP Phase 2 issues", APEX ran one search (at most 5 documents),
read 3 notes and missed ~11 more; and HB marked the research answer "Backend action check: this turn ended with a promise". Searches now
return up to 10 documents and say when more match, the research method asks for breadth and links, and research answers get no coding warning."""
import json

from core import apex_knowledge, hb_learning
from core.apex_tools import ReadOnlyRepository, run_apex_tools

ANSWER = ('SAP Note 3660828 fixes the CE report performance. Other STP2 problems would need to be identified by fetching the relevant '
          'notes (e.g. via /notes add <number>).')


def _run(tmp_path, question):
    calls = []

    def model(_name, msgs):
        calls.append(1)
        return json.dumps({'tool_calls': [], 'answer': ANSWER}), 1
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': question}], lambda: True, lambda _r: None,
                                  ReadOnlyRepository(tmp_path), proposal_handler=lambda *a, **k: {'status': 'succeeded'})
    return answer or '', calls


def test_practice_127_a_research_answer_gets_no_coding_warning(tmp_path):
    answer, calls = _run(tmp_path, 'What do our SAP notes say about STP Phase 2 issues? List the main problems and fixes and cite the notes.')
    assert 'Backend action check' not in answer and len(calls) == 1


def test_practice_127_a_change_request_still_gets_it(tmp_path):
    answer, calls = _run(tmp_path, 'Fix the STP2 report in core/stp.py and add a test.')
    assert 'Backend action check' in answer or len(calls) > 1


def test_practice_127_research_method_asks_for_breadth_and_links():
    m = hb_learning.research_method()
    assert 'search at least twice with different wordings' in m and 'List EVERY matching note' in m
    assert 'Follow the links between notes' in m and 'Never say there is nothing more after one search' in m


def test_practice_127_search_returns_more_and_says_so(monkeypatch):
    src = open(apex_knowledge.__file__).read()
    assert "library=grouped('NOT '+hb_kind,10)" in src and "'items':items[:12]" in src and "'more_matches':True" in src
