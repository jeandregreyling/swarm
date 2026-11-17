"""Practice 136 (owner 17 Nov 2026): APEX's STP2 answer listed all 13 STP2 notes but by title only - it read 5 notes one per round and
ran out of rounds. Every indexed note in a search result now carries a one-line summary (its Symptom's first sentence), and a research
answer of titles only goes back once."""
import json

import core.apex_tools as t
from core import apex_knowledge as k, hb_note_index as ni
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'
TITLES = [('3749998', 'PDS - Introducing SSID for STP2 Reporting via SSP'), ('3671186', 'Error in STP-2 Australia Tax Data Upload Utility Report'),
          ('3710504', 'STP2: Authorization error after implementing Note 3660828'), ('3660828', 'STP2: Performance improvements for CE')]
BARE = ('The Knowledge Centre contains 4 SAP Notes that reference STP Phase 2:\n'
        '1. SAP Note 3749998 – *PDS – Introducing SSID for STP2 Reporting via SSP* (receipt c26420a0f7634da5aad489481fa75149)\n'
        '2. SAP Note 3671186 – *Error in STP‑2 Australia Tax Data Upload Utility Report* (receipt 49465af2312742bb91544906741db977)\n'
        '3. SAP Note 3710504 – *STP2: Authorization error after implementing Note 3660828* (not yet read – receipt not available)\n'
        '4. SAP Note 3660828 – *STP2: Performance improvements for CE* (not yet read – receipt not available)\n')
FULL = ('1. 3749998 (SSID via SSP): customers who send STP through a sending service provider must now include the software subscription ID.\n'
        '2. 3671186 (tax data upload): the upload utility RPAUTAXCOPCRE dumps on a duplicate key; the note corrects the program.\n'
        '3. 3710504 (authorization error): after 3660828 an authorization check on infotype 0712 fails; this note adds the missing check.\n'
        '4. 3660828 (CE performance): the concurrent employment report runs slowly for large employee sets; code corrections speed it up.\n')


def _result():
    return {'status': 'found', 'matches': [f'SAP Note {n}: {n} - {title} | Something goes wrong in {n}.' for n, title in TITLES]}


def _receipt():
    return {'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'STP2'}, 'output': json.dumps(_result())}


def test_practice_136_brief_is_the_first_sentence():
    assert ni.brief('The Australian government has announced new Payday Super legislation (PDS), effective from July 1, 2026. More.') == \
        'The Australian government has announced new Payday Super legislation (PDS), effective from July 1, 2026.'
    assert ni.brief('x' * 400).endswith('...') and len(ni.brief('x' * 400)) == 160 and ni.brief('') == ''


def test_practice_136_matches_carry_the_summary_and_the_result_fits():
    items = [{'document_id': i, 'source_id': i, 'title': f'SAP Note 37{i:05d}: 37{i:05d} - STP2: Problem number {i}', 'excerpt': 'e' * 650,
              'summary': f'On execution of report {i} for a large set of employees, a performance issue is observed in the system.',
              'tags': '["sap-note"]', 'source_ref': f'sap://note/37{i:05d}', 'store': 'knowledge_sources'} for i in range(12)]
    fam = [{'component': 'PY-AU-STP', 'count': 20, 'notes': [f'SAP Note 36{i:05d}: STP2: family member number {i} of the component' for i in range(20)],
            'hint': 'h'}]
    r = k._fit({'status': 'found', 'source': 's', 'query': 'STP2', 'families': fam, 'items': items, 'notice': 'n' * 300})
    assert len(json.dumps(r)) <= k.FIT_CHARS and len(r['matches']) == 12
    assert ' | On execution of report 0 for a large set' in r['matches'][0]
    assert r['items'][0] == {'document_id': 0, 'source_ref': 'sap://note/3700000'}


def test_practice_136_titles_only_is_recognised():
    assert t.titles_only(BARE, [_receipt()])
    assert not t.titles_only(FULL, [_receipt()])
    assert not t.titles_only('Only 3660828 matters here.', [_receipt()])


def test_practice_136_a_titles_only_answer_goes_back(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    seen = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'STP2'}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'Single Touch Payroll Phase 2'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': BARE}), json.dumps({'tool_calls': [], 'answer': FULL})]

    def model(_name, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=lambda name, args: _result())
    assert any(s.startswith('BACKEND CONTENT CHECK') for s in seen) and 'software subscription ID' in answer
