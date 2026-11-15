"""Practice 90 (owner 16 Nov 2026): "why isn't it showing me the status?" - 2,167 SAP notes in six jobs and nothing in chat until a whole
job of 400 ended. /notes now opens with one overall line, and the running job posts that line in JD's chat every PROGRESS_S."""
import json
import sqlite3

from core import hb_sap_note_job as j


def _db(now):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, source_ref TEXT)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'why isn''t it showing me the status?')")
    j.ensure_schema(c)
    rows = [(-1, 'done', [str(n) for n in range(1000000, 1000400)], 400), (-2, 'running', [str(n) for n in range(2000000, 2000400)], 100),
            (-3, 'pending', [str(n) for n in range(3000000, 3000367)], 0)]
    for sid, state, nums, got in rows:
        c.execute('INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, added, had, failed, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (sid, 'pasted', 'pasted', json.dumps(nums), state, json.dumps(nums[:got]), '[]', '[]', now - 3000, now))
    return c


def test_practice_90_one_overall_line():
    import time
    now = time.time()
    line = j.overview(_db(now), now)
    assert line.startswith('📚 SAP notes download: 500 of 1,167 in the Knowledge Centre, 0 failed, 667 to go (about ')
    assert 'left' in line
    assert j.command(_db(now), []).splitlines()[-1].startswith('📚 SAP notes download: 500 of 1,167')


def test_practice_90_nothing_downloading_says_so():
    c = sqlite3.connect(':memory:')
    j.ensure_schema(c)
    assert j.overview(c) is None


def test_practice_90_the_running_job_posts_progress_in_jds_chat():
    import time
    now = time.time()
    c = _db(now)
    j.run(c, -3, fetch=lambda n: (True, f'SAP Note {n}: t'), keep=lambda conn, n, t: None, sleep=lambda s: None, progress_every=0)
    said = [r[0] for r in c.execute("SELECT content FROM messages WHERE conversation_id=2845 AND from_agent='hummingbird'")]
    assert any(s.startswith('📚 SAP notes download:') for s in said)
