"""Practice 68 (15 Nov): the first live SAP notes job died at once ("NoneType is not subscriptable") - its thread looked for the job row
before HB's loop had committed it - and background jobs must not hold the database while they wait on SAP or the mail server."""
import json
import sqlite3
import time
import core.hb_sap_note_job as j
import core.hb_email_intake as e


def db(path):
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    c.execute("CREATE TABLE IF NOT EXISTS knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, raw_text TEXT, domain_tags TEXT, source_ref TEXT, status TEXT DEFAULT 'active')")
    j.ensure_schema(c)
    c.commit()
    return c


def test_practice_68_the_job_waits_until_its_row_is_committed(tmp_path):
    path = tmp_path / 'hb.sqlite'
    loop, worker = db(path), db(path)
    loop.execute("INSERT INTO hb_sap_note_jobs(source_id, title, numbers, state, created_at, updated_at) VALUES (7, 'x.xlsx', '[\"2382421\"]', 'pending', 1, 1)")
    assert j.visible(worker, 7) is False                 # not committed yet: the old code crashed here
    loop.commit()
    assert j.visible(worker, 7) is True


def test_practice_68_no_write_lock_is_held_while_sap_is_asked(tmp_path):
    path = tmp_path / 'hb.sqlite'
    worker, other = db(path), sqlite3.connect(path, timeout=0.2)
    worker.execute("INSERT INTO hb_sap_note_jobs(source_id, title, numbers, state, created_at, updated_at) VALUES (7, 'x.xlsx', '[\"2382421\", \"1999997\"]', 'pending', 1, 1)")
    worker.commit()
    seen = []

    def fetch(number):                                   # while "SAP" is being asked, another HB process must be able to write
        other.execute("INSERT INTO messages(conversation_id, content) VALUES (1, 'someone else writes')")
        other.commit()
        seen.append(number)
        return True, f'SAP Note {number}: t'
    state = j.run(worker, 7, fetch=fetch, keep=lambda conn, n, t: conn.execute("INSERT INTO knowledge_sources(title, source_ref) VALUES (?,?)", (t, f'sap://note/{n}')),
                  sleep=lambda s: None, commit=worker.commit)
    assert state == 'done' and seen == ['2382421', '1999997']
    assert json.loads(worker.execute('SELECT added FROM hb_sap_note_jobs').fetchone()[0]) == seen


def test_practice_68_a_job_cut_off_by_a_restart_goes_back_in_line():
    c = db(':memory:')
    old = time.time() - j.STALE_S - 5
    c.execute("INSERT INTO hb_sap_note_jobs(source_id, title, numbers, state, created_at, updated_at) VALUES (7, 'x.xlsx', '[]', 'running', ?, ?)", (old, old))
    c.execute("INSERT INTO hb_sap_note_jobs(source_id, title, numbers, state, created_at, updated_at) VALUES (8, 'y.xlsx', '[]', 'running', ?, ?)", (time.time(), time.time()))
    assert j._RUNNING.acquire(blocking=False)            # pretend a job thread is busy so tick only tidies up
    try:
        assert j.tick(c) is None
    finally:
        j._RUNNING.release()
    assert dict(c.execute('SELECT source_id, state FROM hb_sap_note_jobs')) == {7: 'pending', 8: 'running'}


def test_practice_68_mail_check_commits_before_it_talks_to_the_mail_server():
    import inspect
    src = inspect.getsource(e.check)
    assert src.index('conn.commit()') < src.index('box = mailbox()') and src.count('conn.commit()') >= 2
