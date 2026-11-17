"""Practice 151 (owner 18 Nov 2026): the STP2 answer listed all 16 notes but said five 'could not be retrieved (not_found)': the
family list gave no document ids, APEX guessed, HB refused the guesses. Family entries now carry the id, and a final answer that calls a
held note missing gets HB's correction."""
import sqlite3

import core.hb_note_index as ni
import core.apex_tools as t


def test_practice_151_family_entries_carry_the_id():
    c = sqlite3.connect(':memory:')
    ni.ensure(c)
    for note, sid, title in [('3700339', 5, 'SAP Note 3700339: 3700339 - RPUSTOQ0 - New option to exclude override entries'),
                             ('3660828', 6, 'SAP Note 3660828: 3660828 - STP2: Performance improvements for CE')]:
        c.execute('INSERT INTO hb_note_index(note, source_id, title, component) VALUES (?,?,?,?)', (note, sid, title, 'PY-AU-STP'))
    fam = ni.families(c, ['PY-AU-STP', 'PY-AU-STP'])
    assert f'SAP Note 3700339: [document_id {(1 << 40) + 5}] RPUSTOQ0 - New option to exclude override entries' in fam[0]['notes']


def test_practice_151_ids_from_families_are_known():
    import json
    out = json.dumps({'matches': [], 'families': [{'component': 'PY-AU-STP', 'notes': ['SAP Note 3700339: [document_id 1099511640000] RPUSTOQ0 - x']}]})
    rec = [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'STP2'}, 'output': out}]
    assert t.note_ids(rec) == {'3700339': 1099511640000}
    assert t._search_results(rec)[0][1] == [('3700339', 'RPUSTOQ0 - x')]
