"""Practice 207: the task packet always fits - many pinned chat messages, or a pasted email as the objective."""
import json
import sqlite3

import pytest

from core import hb_tasks


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, '
              'message_type TEXT, tokens_used INT)')
    hb_tasks.ensure_schema(c)
    return c


def say(c, text):
    return c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content) VALUES (7,'user','apex',?)", (text,)).lastrowid


def test_many_pinned_chat_messages_fit(conn):
    task = hb_tasks.bind(conn, 7, say(conn, 'Chat with JD'), title='Chat with JD', studio=False)
    for n in range(70):
        hb_tasks.bind(conn, 7, say(conn, f'message {n}: ' + 'please do the thing properly ' * 8), task_id=task['task_id'])
    q = 'Is APEX running now?'
    hb_tasks.bind(conn, 7, say(conn, q), task_id=task['task_id'])
    p = hb_tasks.packet(conn, hb_tasks.get(conn, task['task_id']))
    assert len(json.dumps(p)) <= 10000
    assert p['instructions'][-1]['content'] == q
    assert p['older_instructions']['count'] >= 58


def test_pasted_email_objective_fits(conn):
    big = 'Stack ' + 'email body ' * 50000
    task = hb_tasks.bind(conn, 7, say(conn, big), title='Stack', objective=big, studio=False)
    p = hb_tasks.packet(conn, hb_tasks.get(conn, task['task_id']))
    assert len(json.dumps(p)) <= 10000
    assert p['objective_reference']['bytes'] > 500000 and p['objective'].startswith('Stack')


def test_huge_current_instruction_fits(conn):
    task = hb_tasks.bind(conn, 7, say(conn, 'Chat with JD'), title='Chat with JD', studio=False)
    hb_tasks.bind(conn, 7, say(conn, 'EMAIL ' + 'y' * 400000), task_id=task['task_id'])
    p = hb_tasks.packet(conn, hb_tasks.get(conn, task['task_id']))
    assert len(json.dumps(p)) <= 10000
    assert p['instructions'][-1]['reference']['bytes'] > 400000 and p['instructions'][-1]['content'].startswith('EMAIL')
