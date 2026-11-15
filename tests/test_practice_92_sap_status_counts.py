"""Practice 92 (owner 16 Nov 2026): the SAP download status said "448 of 2,194 ... 7 failed ... about 7 h 32 min left" while about 13 notes
a minute were arriving. Each note now counts once, a retried note that came in is not failed, and the time left comes from the last
15 minutes of notes saved in the Knowledge Centre."""
import json
import sqlite3
import time

from core import hb_sap_note_job as j


def test_practice_92_counts_once_and_estimates_from_recent_speed():
    now = time.time()
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, source_ref TEXT, created_at TEXT)')
    j.ensure_schema(c)
    first = [str(n) for n in range(1000000, 1000020)]
    rest = [str(n) for n in range(1000020, 1001020)]
    jobs = [(-1, 'done', first, first[7:], first[:7], now - 7200),          # the test run: 13 in, 7 failed
            (-2, 'done', first[:7], first[:7], [], now - 7000),             # the 7 retried and in
            (-3, 'running', rest, rest[:300], [], now - 1800)]
    for sid, state, nums, added, failed, at in jobs:
        c.execute('INSERT INTO hb_sap_note_jobs(source_id, title, sheet, numbers, state, added, had, failed, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (sid, 'pasted', 'pasted', json.dumps(nums), state, json.dumps(added), '[]', json.dumps(failed), at, now))
    for i, n in enumerate(first + rest[:300]):     # the last 150 of them saved in the last 15 minutes
        at = now - 60 if i >= len(first) + 150 else now - 3600
        c.execute("INSERT INTO knowledge_sources(source_ref, created_at) VALUES (?, datetime(?, 'unixepoch'))", (f'sap://note/{n}', at))
    line = j.overview(c, now)
    assert line.startswith('📚 SAP notes download: 320 of 1,020 in the Knowledge Centre, 0 failed, 700 to go (about 1 h 10 min left)'), line
