"""Practice 97 (owner 16 Nov 2026): "find notes that haven't been downloaded and do research" on Australian and general payroll. SAP for Me
has no search HB may use, so HB reads its saved PY-AU / PY-XX notes, fetches the notes they cite, and follows those a few levels deep."""
import json
import sqlite3

from core import hb_sap_note_job as j


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, source_ref TEXT, raw_text TEXT)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'yes, do research')")
    j.ensure_schema(c)
    return c


def _note(c, n, comp, body):
    c.execute('INSERT INTO knowledge_sources(source_ref, raw_text) VALUES (?, ?)',
              (f'sap://note/{n}', f'SAP Note {n}: {n} - title\ncomponent {comp} | version 2 | released 16.10.2026\n{body}'))


def test_practice_97_what_a_note_cites():
    text = ('SAP Note 3702280: t\ncomponent PY-AU\nSee SAP Note 2345678 and KBA 3123456.\n'
            'Related SAP Notes: 2999001, 3100002\nhttps://me.sap.com/notes/1234567\n'
            'The cap is 1500000 dollars from 2026.\n')
    assert j.cited(text, '3702280') == ['2345678', '3123456', '1234567', '2999001', '3100002']


def test_practice_97_follows_only_payroll_notes_and_only_what_is_missing():
    c = _db()
    _note(c, '3702280', 'PY-AU', 'See SAP Note 2345678 and SAP Note 3755729.')
    _note(c, '3755729', 'PY-AU-STP', 'Single Touch Payroll; see SAP Note 3001001.')
    _note(c, '3000500', 'PY-XX-BS', 'Related SAP Notes: 2999001, 3001001')
    _note(c, '1613622', 'PY-SI', 'Slovenia; see SAP Note 1111111.')
    c.execute("INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, created_at, updated_at) VALUES (-9, 'p', 'pasted', ?, 'pending', 0, 0)",
              (json.dumps(['2999001']),))
    line = j.follow(c, now=1000.0)
    nums = json.loads(c.execute("SELECT numbers FROM hb_sap_note_jobs WHERE sheet='follow:PY-AU,PY-XX:3'").fetchone()[0])
    assert nums == ['2345678', '3001001']                      # not 3755729 (have it), 2999001 (queued), 1111111 (Slovenia)
    assert '3 saved PY-AU, PY-XX notes cite 2 SAP notes' in line
    said = c.execute("SELECT conversation_id, content FROM messages WHERE from_agent='hummingbird'").fetchall()
    assert said[-1][0] == 2845 and said[-1][1].startswith('🔎 Research:')


def test_practice_97_goes_one_level_deeper_when_a_level_is_in_and_stops_at_the_last():
    c = _db()
    _note(c, '3702280', 'PY-AU', 'See SAP Note 2345678.')
    j.follow(c, depth=2, now=1000.0)
    assert j.next_level(c) is None                             # still downloading
    c.execute("UPDATE hb_sap_note_jobs SET state='done'")
    _note(c, '2345678', 'PY-AU', 'See SAP Note 2456789.')       # the cited note came in and cites another
    assert 'cite 1 SAP notes' in j.next_level(c)
    assert json.loads(c.execute("SELECT numbers FROM hb_sap_note_jobs WHERE sheet='follow:PY-AU,PY-XX:1'").fetchone()[0]) == ['2456789']
    c.execute("UPDATE hb_sap_note_jobs SET state='done'")
    assert j.next_level(c) is None                             # depth 1 was the last level
    assert j.next_level(c) is None                             # and nothing repeats


def test_practice_97_the_notes_follow_command():
    c = _db()
    _note(c, '3702280', 'PY-AU', 'See SAP Note 2345678.')
    assert 'cite 1 SAP notes' in j.command(c, ['follow', 'PY-AU'])
    assert not c.execute("SELECT 1 FROM messages WHERE from_agent='hummingbird'").fetchone()     # the command answers; no extra line
