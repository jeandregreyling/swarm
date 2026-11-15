"""Practice 89 (owner 16 Nov 2026): JD typed "ok go on and download all the motes" and APEX answered "cannot be fulfilled with the
current permissions" - it had tried the model-archive download tool. Downloading SAP notes is HB's own job: HB recognises the request,
takes the numbers from JD's pasted list, and queues the SAP notes job itself."""
import json
import sqlite3

from core import hb_sap_note_job as job
from core.hb_owner_intent import classify

PASTE = "Stack\tNumber\tURL\n" + "\n".join(f"SAPKE608G4\t{n}\thttps://launchpad.support.sap.com/#/notes/{n}" for n in range(3640475, 3640475 + 450))


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, source_ref TEXT)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', ?)", (PASTE,))
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'apex', 'ok')")
    c.execute("INSERT INTO knowledge_sources(source_ref) VALUES ('sap://note/3640475')")
    return c


def test_practice_89_download_the_notes_is_hb_work():
    for text in ('ok go on and download all the motes', 'download the SAP notes', 'fetch the rest of the notes please',
                 'can you download those notes'):
        assert classify(text) == 'sap_notes', text
    for text in ('download the qwen model', 'write the release notes', 'download the release notes for llama.cpp'):
        assert classify(text) != 'sap_notes', text


def test_practice_89_hb_queues_the_pasted_list_in_jobs_skipping_what_it_has():
    c = _db()
    text = job.from_chat(c, 2845, 'ok go on and download all the motes', now=1000.0)
    jobs = c.execute('SELECT numbers, state FROM hb_sap_note_jobs ORDER BY created_at').fetchall()
    assert [len(json.loads(n)) for n, _ in jobs] == [400, 49] and {s for _, s in jobs} == {'pending'}
    assert 'Downloading 449 SAP notes from the list you pasted earlier' in text and '1 already in the Knowledge Centre' in text
    again = job.from_chat(c, 2845, 'download all the notes', now=2000.0)
    assert again.startswith('📚 Nothing new to download') and c.execute('SELECT COUNT(*) FROM hb_sap_note_jobs').fetchone()[0] == 2


def test_practice_89_numbers_in_the_message_itself_and_nothing_found():
    c = _db()
    assert job.numbers_in('please get note 3811103 and SAP Note 3802510') == ['3811103', '3802510']
    assert job.numbers_in('3840422 Dynamic calls after SAP Note 3430313 https://launchpad.support.sap.com/#/notes/3840422') == ['3840422']
    assert job.numbers_in('call me at 0491 on 20261116') == []
    empty = sqlite3.connect(':memory:')
    empty.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, content TEXT)')
    assert 'found no SAP note numbers' in job.from_chat(empty, 1, 'download all the notes')
