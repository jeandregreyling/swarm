"""Practice 144 (owner 17 Nov 2026, "keep going asking and checking the answer till it's right"): SAP Note 3713786 defines the MCB but
its title and Symptom do not say so, so APEX never read it. A search result whose title lacks the query words shows the note's own
sentences that carry them."""
import sqlite3

import core.hb_note_index as ni

TEXT = ('SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super\nSymptom\nFrom 1 July 2026 employers must pay super on payday.\n'
        'Maximum Contribution Base (MCB): From July 1, 2026, the maximum contribution base(MCB) check is changing from Quarterly to an '
        'Annual amount of 270,830 AUD. MCB is the upper limit of your employee\'s earnings for each financial year for which you need to '
        'pay super guarantee (SG).\nSome unrelated sentence about evaluation classes and wage types here.')


def test_practice_144_matched_line():
    line = ni.matched_line(TEXT, 'MCB cap SAP note')
    assert '270,830 AUD' in line and len(line) <= 300
    assert ni.matched_line(TEXT, 'STP2 reporting') == ''


def test_practice_144_title_check():
    assert ni._title_has('Pay Day Super Phase 2.0 - Maximum Contribution Base (MCB) Enhancements', 'MCB cap')
    assert not ni._title_has('Phase 1 Payroll Changes for Payday Super', 'MCB cap SAP note')


def test_practice_144_rank_uses_the_matched_line(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, raw_text TEXT)')
    db.execute('INSERT INTO knowledge_sources VALUES (7004, ?)', (TEXT,))
    db.execute('INSERT INTO knowledge_sources VALUES (6655, ?)', ('MCB check extended to non-SG funds.',))
    hits = [{'source_id': 7004, 'title': 'SAP Note 3713786: 3713786 - Phase 1 Payroll Changes for Payday Super', 'symptom': 'From 1 July 2026 employers must pay super on payday.',
             'tags': '', 'note': '3713786', 'component': 'PY-AU'},
            {'source_id': 6655, 'title': 'SAP Note 3793457: 3793457 - Maximum Contribution Base (MCB) Enhancements', 'symptom': 'The MCB check now covers non-SG funds.',
             'tags': '', 'note': '3793457', 'component': 'PY-AU-SUP'}]
    monkeypatch.setattr(ni, 'search', lambda conn, q, limit: hits)
    monkeypatch.setattr(ni, 'families', lambda conn, comps: [])
    items, _f = ni.rank(db, 'MCB cap', [], 1 << 40)
    assert items[0]['summary'].startswith('says: ') and '270,830' in items[0]['summary']
    assert items[1]['summary'] == 'The MCB check now covers non-SG funds.'
