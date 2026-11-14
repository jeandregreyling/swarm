"""Studio stays tidy: questions don't create steps; finished HB tasks close their auto step."""
import sqlite3

import pytest

from core import hb_tasks


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT,
                              message_type TEXT, tokens_used INT, created_at TEXT);
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, name TEXT, description TEXT, methodology TEXT, status TEXT, owner TEXT,
                              created_at REAL, updated_at REAL);
        CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT,
                                   order_idx INT, created_at REAL, updated_at REAL, residual_risk TEXT);
    """)
    hb_tasks.ensure_schema(c)
    yield c
    c.close()


def say(c, text):
    mid = c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(2834,'user','apex',?,'chat')",
                    (text,)).lastrowid
    return hb_tasks.bind(c, 2834, mid)


@pytest.mark.parametrize('text,question', [
    ('@apex what are you doing?', True),
    ('How is the sundial reading VRAM', True),
    ('@apex fix the sundial so it shows VRAM', False),
    ('Can you build the nanny bot?', False),                 # a question that asks for work is work
    ('Continue the DREAM build', False),
])
def test_plain_questions_are_recognised(text, question):
    assert hb_tasks.is_plain_question(text) is question


def test_questions_get_no_studio_step_but_instructions_do(conn):
    q = say(conn, '@apex what are you doing?')
    w = say(conn, '@apex fix the sundial VRAM reading')
    assert q['step_id'] is None and q['project_id'] is None
    assert w['step_id'] and conn.execute('SELECT status FROM project_steps WHERE step_id=?', (w['step_id'],)).fetchone()[0] == 'todo'


def test_finished_tasks_close_their_auto_step_but_curated_steps_wait_for_the_owner(conn):
    done = say(conn, 'Fix the sundial VRAM reading')
    dropped = say(conn, 'Build the old media teaser')
    open_ = say(conn, 'Index the SAP payroll notes')
    conn.execute("INSERT INTO projects VALUES('P-CURATED001','Plan','','agile','active','jd',0,0)")
    conn.execute("INSERT INTO project_steps VALUES('S-CURATED001','P-CURATED001','Curated','','partial','apex',0,0,0,'')")
    curated = say(conn, 'Curated plan step work')
    conn.execute("UPDATE hb_tasks SET project_id='P-CURATED001', step_id='S-CURATED001' WHERE task_id=?", (curated['task_id'],))
    conn.execute("UPDATE hb_tasks SET state='completed' WHERE task_id IN (?,?)", (done['task_id'], curated['task_id']))
    conn.execute("UPDATE hb_tasks SET state='cancelled' WHERE task_id=?", (dropped['task_id'],))
    assert hb_tasks.sync_studio_steps(conn) == 2
    status = lambda t: conn.execute('SELECT status FROM project_steps WHERE step_id=?', (t['step_id'],)).fetchone()[0]
    assert status(done) == 'done' and status(dropped) == 'skipped' and status(open_) == 'todo'
    assert conn.execute("SELECT status FROM project_steps WHERE step_id='S-CURATED001'").fetchone()[0] == 'partial'
    assert hb_tasks.sync_studio_steps(conn) == 0


def test_a_bare_yes_joins_the_task_being_discussed(conn):
    work = say(conn, '@apex check why the GPU is so full')
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,created_at) "
                 "VALUES(2834,'apex','user','Shall I unload the idle 7B model?','chat',datetime('now'))")
    hb_tasks.bind(conn, 2834, conn.execute('SELECT MAX(id) FROM messages').fetchone()[0], task_id=work['task_id'], kind='reply')
    assert hb_tasks.reply_target(conn, 2834, 'yes') == work['task_id']
    assert hb_tasks.reply_target(conn, 2834, 'Go ahead please!') == work['task_id']
    assert hb_tasks.reply_target(conn, 2834, 'yes, and also rebuild the sundial') is None      # real content: a new task
    conn.execute("UPDATE hb_tasks SET state='completed' WHERE task_id=?", (work['task_id'],))
    assert hb_tasks.reply_target(conn, 2834, 'yes') is None                                   # finished tasks are not reopened
