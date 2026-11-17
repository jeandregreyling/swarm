"""Practice 150 (owner 18 Nov 2026, "1 then 2"): the STP2 answer still missed PY-AU-STP notes without 'STP' in the title (3700339,
3677472, 3770618), said "No additional notes were returned" above HB's own list, and did not say what it could not find."""
import json

import core.apex_tools as t

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'
QM = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
OUT = json.dumps({'matches': ['SAP Note 3660828: [document_id 1] 3660828 - STP2: Performance improvements for CE | slow'],
                  'families': [{'component': 'PY-AU-STP', 'notes': ['SAP Note 3660828: STP2: Performance improvements for CE',
                                                                    'SAP Note 3700339: RPUSTOQ0 - New option to exclude override entries']},
                               {'component': 'PY-AU-SUP', 'notes': ['SAP Note 3793457: Pay Day Super Phase 2.0 - MCB Enhancements',
                                                                    'SAP Note 3795765: PY-AU-PS: RESC not calculated at fund level']}]})
REC = [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'STP2'}, 'output': OUT}]


def test_practice_150_family_of_the_topic_counts():
    assert t.topic_family(REC, ['STP']) == {'3660828', '3700339'}
    assert t.topic_family(REC, ['MCB']) == set()
    left = t.notes_left_out(Q, 'SAP Note 3660828 makes the CE report faster.', REC)
    assert any(s.startswith('3700339') for s in left)
    assert not any(s.startswith('3795765') for s in t.notes_left_out(QM, 'SAP Note 3793457.', REC))


def test_practice_150_nothing_more_claims_are_dropped():
    a = ('1. SAP Note 3660828 - faster CE report.\nAll three notes are the relevant STP-2-related issues identified in the Knowledge '
         'Centre for Australian payroll. No additional notes were returned for the query.\nNo further action is required.')
    out = t.drop_nothing_more(a)
    assert '3660828' in out and 'No additional notes' not in out and 'relevant STP-2-related issues identified' not in out
    assert 'No further action is required' not in out


def test_practice_150_not_checked_line():
    assert 'Not checked' in t.not_checked_line(Q, 'SAP Note 3660828 makes the CE report faster.')
    assert t.not_checked_line(Q, 'I could not find a note on X.') == ''
    assert t.not_checked_line(QM, 'x') == ''
