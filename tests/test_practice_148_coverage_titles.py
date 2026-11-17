"""Practice 148 (owner 17 Nov 2026): after hybrid search (Practice 147) the coverage check matched 'MCB' in the Spanish SI note's passage
and made APEX include it, and the read check (3 notes, in the answer's order) never asked for 3713786, which defines the Australian MCB."""
import json

import core.apex_tools as t

Q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
L = 1 << 40
OUT = json.dumps({'matches': [
    'SAP Note 3713786: [document_id 1099511634780] 3713786 - Phase 1 Payroll Changes for Payday Super | says: Maximum Contribution Base (MCB): annual 270,830 AUD',
    'SAP Note 3793457: [document_id 1099511634431] 3793457 - Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements | x',
    'SAP Note 3808818: [document_id 1099511634435] 3808818 - PDS Phase 2.1: MCB check extended | y',
    'SAP Note 3749754: [document_id 1099511634413] 3749754 - Payday Super: MCB flag not updated in V_T5QSF | z',
    'SAP Note 3800283: [document_id 1099511633216] 3800283 - Year-end legal change 2026_27 - SI constants | says: Daily MCB for regular payments: EUR 247.00']})
REC = [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'MCB'}, 'output': OUT}]


def test_practice_148_coverage_looks_at_titles_only():
    left = t.notes_left_out(Q, 'Notes 3713786, 3793457, 3808818 and 3749754.', REC)
    assert left == []


def test_practice_148_read_check_puts_the_best_notes_first():
    todo = [n for n, _d in t.notes_to_read('SAP Note 3793457, SAP Note 3808818 and SAP Note 3749754.', REC)]
    assert len(todo) == 4 and todo[0] == '3713786' and '3800283' not in todo
