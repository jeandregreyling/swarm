"""Practice 70 (owner 15 Nov): every email, inbox file and SAP notes job has its step in Studio - names, counts and ids only."""
import sqlite3
import core.hb_intake_records as r


def db():
    c = sqlite3.connect(':memory:')
    c.execute("CREATE TABLE projects(project_id TEXT, name TEXT NOT NULL, description TEXT, methodology TEXT NOT NULL DEFAULT 'mixed', status TEXT NOT NULL DEFAULT 'active', owner TEXT NOT NULL DEFAULT 'seven', created_at REAL NOT NULL, updated_at REAL)")
    c.execute("CREATE TABLE project_steps(step_id TEXT, project_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT, status TEXT NOT NULL DEFAULT 'todo', owner TEXT NOT NULL DEFAULT 'seven', order_idx INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL)")
    c.execute('CREATE TABLE hb_email_seen(message_id TEXT PRIMARY KEY, sender TEXT, subject TEXT, outcome TEXT, kc_sources TEXT, at REAL)')
    c.execute('CREATE TABLE hb_sap_note_jobs(source_id INTEGER PRIMARY KEY, title TEXT, sheet TEXT, numbers TEXT, state TEXT, added TEXT, had TEXT, failed TEXT, note TEXT, created_at REAL, updated_at REAL)')
    c.executemany('INSERT INTO hb_email_seen VALUES (?,?,?,?,?,?)', [
        ('<m1>', 'jd@example.com', 'Pay run sheet', 'taken in', '11,12', 1.0),
        ('<m2>', 'jd@corp.example', 'Protected one', 'taken in', '', 2.0),
        ('<m3>', 'spam@evil.test', 'Hello', 'left alone: not a trusted sender', '', 3.0),
        ('file://notes.xlsx/1/2', 'inbox folder', 'notes.xlsx', 'taken in', '13', 4.0)])
    c.execute("INSERT INTO hb_sap_note_jobs VALUES (13, 'Inbox file: notes.xlsx', 'Needs check', '[\"1\",\"2\",\"3\"]', 'running', '[\"1\"]', '[]', '[]', '', 5.0, 5.0)")
    return c


def steps(c):
    return {t: (s, d) for t, s, d in c.execute('SELECT title, status, description FROM project_steps')}


def test_practice_70_every_arrival_and_job_has_a_studio_step():
    c = db()
    assert r.sync(c, now=10.0) == 4
    assert c.execute('SELECT name, owner FROM projects').fetchall() == [(r.PROJECT, 'hummingbird')]
    s = steps(c)
    assert s['Email: Pay run sheet (jd@example.com)'][0] == 'done' and 'KC11, KC12' in s['Email: Pay run sheet (jd@example.com)'][1]
    assert s['Email: Protected one (jd@corp.example)'][0] == 'blocked' and 'Nothing in it could be read' in s['Email: Protected one (jd@corp.example)'][1]
    assert s['File: notes.xlsx'][0] == 'done' and 'Dropped into the inbox folder' in s['File: notes.xlsx'][1]
    assert s['SAP notes: Inbox file: notes.xlsx'][0] == 'doing' and '3 SAP Note / KBA number(s): 1 added' in s['SAP notes: Inbox file: notes.xlsx'][1]
    assert not any('Hello' in t for t in s)                               # mail HB left alone is not recorded


def test_practice_70_steps_follow_the_job_and_nothing_is_written_twice():
    c = db()
    r.sync(c, now=10.0)
    assert r.sync(c, now=11.0) == 0
    c.execute("UPDATE hb_sap_note_jobs SET state='done', added='[\"1\",\"2\"]', failed='[\"3\"]'")
    assert r.sync(c, now=12.0) == 1
    status, text = steps(c)['SAP notes: Inbox file: notes.xlsx']
    assert status == 'done' and '2 added to the Knowledge Centre, 0 already there, 1 SAP would not give (3)' in text and 'Notes added: 1, 2' in text
    assert c.execute('SELECT COUNT(*) FROM project_steps').fetchone()[0] == 4 and c.execute('SELECT COUNT(*) FROM projects').fetchone()[0] == 1
    c.execute("UPDATE hb_sap_note_jobs SET state='stopped', note='SAP sign-in failed'")
    r.sync(c, now=13.0)
    assert steps(c)['SAP notes: Inbox file: notes.xlsx'][0] == 'blocked'


def test_practice_70_it_runs_in_hb_loop():
    from pathlib import Path
    assert 'intake_records_sync(conn)' in (Path(__file__).resolve().parents[1] / 'core/peer_coordination.py').read_text()
