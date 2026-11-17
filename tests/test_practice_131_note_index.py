"""Practice 131 (owner 17 Nov 2026): "I thought part of the homework would have been to properly index the notes". knowledge_search
matched words in note text: Italian payroll notes outranked STP2 ones, and PY-AU-STP notes without "STP2" in the title were never found.
HB now indexes each note's header, Other Terms and Symptom (FTS5, ranked), and a search lists the component family the top notes share."""
import sqlite3
from contextlib import closing

from core import apex_knowledge, hb_note_index as ni


def _note(n, comp, title, symptom, terms=''):
    return (f'SAP Note {n}: {n} - {title}\ncomponent {comp} | version 2 | released 17.10.2025 | SAP Note | Correction with medium priority\n'
            f'Symptom\n\n{symptom}\n\nOther Terms\n\n{terms}\n\nReason and Prerequisites\n\nSee note 3660828.\n\nSolution\n\nApply it.')


NOTES = [(1, '3660828', 'PY-AU-STP', 'STP2: Performance improvements for CE', 'Single Touch Payroll Phase 2 CE report is slow.', 'STP2 CE'),
         (2, '3700339', 'PY-AU-STP', 'RPUSTOQ0 - New option to exclude override entries', 'Override upload needs an exclusion option.', ''),
         (3, '3708034', 'PY-AU-STP', 'STP2: Incorrect tax treatment code for downwards variation 0%', 'Tax treatment wrong.', 'STP2'),
         (4, '3706319', 'PY-IT', 'CALC: Illness absences reporting in Giorno', 'Australian? No: Italian payroll phase 2 of Uniemens.', ''),
         (5, '3713786', 'PY-AU', 'Phase 1 Payroll Changes for Payday Super', 'Payroll phase 1 changes in Australian payroll.', '')] + \
        [(6 + i, f'39000{i:02d}', 'PY-DE', f'Payroll correction {i}', 'Payroll phase run correction.', '') for i in range(20)]   # STP is rare, as in the KC


def _db(path):
    with closing(sqlite3.connect(path)) as c, c:
        c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY,title TEXT,raw_text TEXT,domain_tags TEXT,source_ref TEXT,'
                  'status TEXT,subcategory TEXT,content_hash TEXT)')
        for sid, n, comp, title, symptom, terms in NOTES:
            c.execute('INSERT INTO knowledge_sources VALUES(?,?,?,?,?,?,?,?)', (sid, f'SAP Note {n}: {n} - {title}',
                      _note(n, comp, title, symptom, terms), '["sap-note"]', f'sap://note/{n}', 'active', 'sap-note', f'h{sid}'))


def test_practice_131_parse_reads_the_header_and_sections():
    f = ni.parse('3660828', _note('3660828', 'PY-AU-STP', 'STP2: Performance', 'CE report is slow.', 'STP2 CE, RPCSTP2Q0_CE'))
    assert (f['component'], f['released'], f['version']) == ('PY-AU-STP', '2025-10-17', 2)
    assert f['symptom'] == 'CE report is slow.' and f['terms'] == 'STP2 CE, RPCSTP2Q0_CE' and f['mentions'] == ''


def test_practice_131_ranked_search_and_whole_families(tmp_path):
    path = tmp_path / 'kc.sqlite'
    _db(path)
    with closing(sqlite3.connect(path)) as c, c:
        assert ni.refresh(c) == 25 and ni.refresh(c) == 0
        c.execute("UPDATE knowledge_sources SET content_hash='changed' WHERE source_id=1")
        assert ni.refresh(c) == 1
        top = [h['note'] for h in ni.search(c, 'STP Phase 2 Australian payroll')]
        assert set(top[:3]) == {'3660828', '3700339', '3708034'}          # STP notes above the Italian and Payday Super ones
        assert ni.fts_query('STP2') == '"stp2"* OR "stp"*'
        fam = ni.families(c, ['PY-AU-STP', 'PY-AU-STP', 'PY-IT'])
        assert len(fam) == 1 and fam[0]['component'] == 'PY-AU-STP' and fam[0]['count'] == 3
        # Practice 151: family entries carry the document id
        assert any(n.startswith('SAP Note 3700339: [document_id ') and n.endswith('] RPUSTOQ0 - New option to exclude override entries')
                   for n in fam[0]['notes'])


def test_practice_131_knowledge_search_uses_the_index(tmp_path, monkeypatch):
    path = tmp_path / 'kc.sqlite'
    _db(path)
    with closing(sqlite3.connect(path)) as c, c:
        ni.refresh(c)
    monkeypatch.setattr(apex_knowledge, 'get_connection', lambda: sqlite3.connect(path))
    r = apex_knowledge.search('STP Phase 2 Australian payroll')
    assert [i['source_ref'] for i in r['items'][:3]].count('sap://note/3706319') == 0
    assert r['families'][0]['component'] == 'PY-AU-STP' and r['families'][0]['count'] == 3
    assert list(r).index('families') < list(r).index('items')
