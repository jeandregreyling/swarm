"""Practice 95 (owner 16 Nov 2026): JD emailed "SAP HRSP F2 to F8" with 2,989 SAP note links pasted into the body. HB saved the email
and never fetched a note, because only spreadsheets became notes jobs. An email body with note links is now a job too."""
import json
import sqlite3

from core import hb_sap_note_job as j


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute("CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, source_ref TEXT, raw_text TEXT, domain_tags TEXT, status TEXT DEFAULT 'active')")
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'I sent you an email with more notes')")
    j.ensure_schema(c)
    return c


def _email(c, sid, body):
    c.execute("INSERT INTO knowledge_sources(source_id, title, source_ref, raw_text, domain_tags) VALUES (?,?,?,?,?)",
              (sid, 'Email: SAP HRSP F2 to F8', f'email://{sid}', body, '["email", "confidential"]'))


ROWS = '\r\n'.join(f'TRUE\r\nSAPKE608F4\r\nPY-AU\r\nAustralia\r\n{n}\r\nhttps://launchpad.support.sap.com/#/notes/{n}'
                    for n in ('3000001', '3000002', '3000003', '3000004'))


def test_practice_95_note_links_in_an_email_body_become_a_job():
    c = _db()
    c.execute("INSERT INTO knowledge_sources(source_id, title, source_ref, raw_text, domain_tags) VALUES (1, 'SAP Note 3000001', 'sap://note/3000001', 't', '[]')")
    _email(c, 7358, 'Email from jd\nSubject: SAP HRSP F2 to F8\n\n' + ROWS)
    assert j.find_new(c) == 1
    state, numbers = c.execute('SELECT state, numbers FROM hb_sap_note_jobs WHERE source_id=7358').fetchone()
    assert state == 'pending' and json.loads(numbers) == ['3000002', '3000003', '3000004']
    said = c.execute("SELECT conversation_id, content FROM messages WHERE from_agent='hummingbird'").fetchall()
    assert said[-1][0] == 2845 and '3 new SAP note(s)' in said[-1][1]
    assert j.find_new(c) == 0                                   # looked at once


def test_practice_95_an_email_whose_notes_are_all_queued_stays_quiet():
    c = _db()
    c.execute("INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, created_at, updated_at) VALUES (-5, 'pasted', 'pasted', ?, 'running', 0, 0)",
              (json.dumps(['3000001', '3000002', '3000003', '3000004']),))
    _email(c, 7358, ROWS)
    assert j.find_new(c) == 0
    assert c.execute('SELECT state FROM hb_sap_note_jobs WHERE source_id=7358').fetchone()[0] == 'nothing to fetch'
    assert not c.execute("SELECT 1 FROM messages WHERE from_agent='hummingbird'").fetchone()


def test_practice_95_an_ordinary_email_is_not_a_job():
    c = _db()
    _email(c, 9, 'Hi, see SAP Note 3000001 about the tax change. Thanks')
    assert j.find_new(c) == 0
    assert not c.execute('SELECT 1 FROM hb_sap_note_jobs').fetchone()
