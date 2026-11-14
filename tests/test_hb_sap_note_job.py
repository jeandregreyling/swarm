"""Practice 66 (owner 15 Nov): a spreadsheet's "needs check" tab becomes SAP Notes in the Knowledge Centre."""
import json
import sqlite3
import core.hb_sap_note_job as j
import core.hb_commands as cmds

SHEET = ('File: notes.xlsx\n\n## Sheet: Summary (2 rows)\nArea\tCount\nPayroll\t3\n\n'
         '## Sheet: Needs Check (5 rows)\nArea\tSAP Note\tComment\nPY-AU\t2382421\tcheck 20261115\nPY-AU\tNote 3012345\t\n'
         'PY-XX\t2382421\tduplicate\nPY-XX\tKBA 1234567, 7654321\t\nPY-XX\tn/a\t99999999\n\n## Sheet: Done (1 rows)\nNote\n1111111')


def test_practice_66_the_needs_check_tab_is_found_whatever_its_spelling():
    blocks = j.sheets(SHEET)
    assert [b[0] for b in blocks] == ['Summary', 'Needs Check', 'Done']
    for name in ('Needs Check', 'needs_check', 'NEED-CHECK', '2. Needs check (open)'):
        assert j.pick([('A', []), (name, [])])[0][0][0] == name
    assert j.pick([('A', []), ('B', [])]) == ([('A', []), ('B', [])], False)


def test_practice_66_numbers_come_from_the_note_column_only():
    p = j.plan(SHEET)
    assert p == {'sheet': 'Needs Check', 'matched': True, 'numbers': ['2382421', '3012345', '1234567', '7654321']}      # not 20261115, 99999999 or 1111111
    assert j.numbers([['x', '2382421.0'], ['SAP Note 123', 'KBA 3012345'], ['12345', 'call 0412345678 now']]) == ['2382421', '3012345']
    assert j.plan('File: n.csv\n\nnote,title\n2382421,network\n3012345,x')['numbers'] == ['2382421', '3012345']


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    c.execute("CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, raw_text TEXT, domain_tags TEXT, source_ref TEXT, status TEXT DEFAULT 'active')")
    c.execute("INSERT INTO knowledge_sources(title, raw_text, domain_tags) VALUES ('Inbox file: notes.xlsx', ?, '[\"inbox-file\", \"confidential\"]')", (SHEET,))
    c.execute("INSERT INTO knowledge_sources(title, raw_text, domain_tags) VALUES ('Inbox file: readme.txt', 'Note 5555555', '[\"inbox-file\", \"confidential\"]')")
    c.execute("INSERT INTO knowledge_sources(title, raw_text, domain_tags, source_ref) VALUES ('SAP Note 3012345', 'x', '[\"sap-note\"]', 'sap://note/3012345')")
    return c


def test_practice_66_a_new_spreadsheet_becomes_a_job_once_and_rows_stay_private():
    c = db()
    assert j.find_new(c) == 1 and j.find_new(c) == 0
    assert c.execute('SELECT source_id, state, sheet FROM hb_sap_note_jobs').fetchall() == [(1, 'pending', 'Needs Check')]
    line = c.execute('SELECT content FROM messages').fetchone()[0]
    assert '4 SAP Note / KBA number(s) found in the tab "Needs Check"' in line and 'PY-AU' not in line and 'duplicate' not in line


def test_practice_66_job_fetches_skips_and_reports():
    c = db()
    j.find_new(c)
    calls, kept = [], []

    def fetch(number):
        calls.append(number)
        return (False, 'SAP returned nothing for that number.') if number == '7654321' else (True, f'SAP Note {number}: title')
    state = j.run(c, 1, fetch=fetch, keep=lambda conn, n, t: kept.append(n), sleep=lambda s: None)
    assert state == 'done' and calls == ['2382421', '1234567', '7654321'] and kept == ['2382421', '1234567']        # 3012345 was already there
    assert [json.loads(x) for x in c.execute('SELECT added, had, failed FROM hb_sap_note_jobs').fetchone()] == [['2382421', '1234567'], ['3012345'], ['7654321']]
    assert '2 added to the Knowledge Centre, 1 already there, 1 SAP would not give (7654321)' in c.execute('SELECT content FROM messages ORDER BY id DESC').fetchone()[0]


def test_practice_66_a_refused_sign_in_stops_the_job_at_once():
    c = db()
    j.find_new(c)
    calls = []
    state = j.run(c, 1, fetch=lambda n: calls.append(n) or (False, 'SAP sign-in failed: the user ID or password was not accepted'), keep=None, sleep=lambda s: None)
    assert state == 'stopped' and calls == ['2382421']
    assert 'Stopped with 4 still to fetch' in c.execute('SELECT content FROM messages ORDER BY id DESC').fetchone()[0]
    assert j.command(c, ['run', 'KC1']).startswith('KC1: 4 SAP Note number(s)') and j.command(c, []).startswith('SAP notes jobs:\n- KC1 ')
    assert 'notes' in cmds.NAMES and cmds.parse('notes run KC12') == ('notes', ['run', 'KC12'])
