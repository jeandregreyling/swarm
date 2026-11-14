"""Practice 69 (owner 15 Nov): /notes add - a pasted list of SAP Note numbers becomes a job, whatever its layout."""
import json
import sqlite3
import core.hb_sap_note_job as j
import core.hb_commands as cmds


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    c.execute("CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, raw_text TEXT, domain_tags TEXT, source_ref TEXT, status TEXT DEFAULT 'active')")
    return c


def test_practice_69_a_pasted_list_becomes_a_job_and_runs():
    c = db()
    args = cmds.parse('notes add 2382421, 1999997\n2000002; #3012345. 12345 2382421 20261115x')[1]
    out = j.command(c, args)
    assert out.startswith('4 SAP Note number(s) taken')
    sid, numbers, state = c.execute('SELECT source_id, numbers, state FROM hb_sap_note_jobs').fetchone()
    assert sid < 0 and json.loads(numbers) == ['2382421', '1999997', '2000002', '3012345'] and state == 'pending'
    kept = []
    assert j.run(c, sid, fetch=lambda n: (True, f'SAP Note {n}: t'), keep=lambda conn, n, t: kept.append(n), sleep=lambda s: None) == 'done'
    assert kept == ['2382421', '1999997', '2000002', '3012345']
    assert '4 added to the Knowledge Centre' in c.execute('SELECT content FROM messages ORDER BY id DESC').fetchone()[0]
    assert j.command(c, ['add', 'none', 'here']).startswith('Give the note numbers')
    assert j.find_new(c) == 0                                 # a pasted job is not mistaken for a spreadsheet
