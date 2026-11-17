"""Practice 139 (owner 17 Nov 2026): JD asked about the MCB cap and nothing happened - the chat's long-lived "Chat with JD" task pinned
a 548 KB pasted email word for word, so hb_tasks.packet raised "Pinned task instructions exceed the context budget" on every turn.
Older owner messages now become references (largest first); the current instruction stays exact."""
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


def test_practice_139_a_huge_old_owner_message_no_longer_blocks_the_chat(conn):
    root = say(conn, 'Chat with JD')
    task = hb_tasks.bind(conn, 7, root, title='Chat with JD', studio=False)
    for text in ['short one', 'EMAIL ' + 'x' * 500000, 'another short one']:
        hb_tasks.bind(conn, 7, say(conn, text), task_id=task['task_id'])
    q = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
    hb_tasks.bind(conn, 7, say(conn, q), task_id=task['task_id'])
    p = hb_tasks.packet(conn, hb_tasks.get(conn, task['task_id']))
    assert len(json.dumps(p)) <= 10000
    assert p['instructions'][-1]['content'] == q
    big = [i for i in p['instructions'] if 'reference' in i]
    assert len(big) == 1 and big[0]['reference']['bytes'] > 500000
    assert big[0]['reference']['read']['tool'] == 'task_evidence'
    assert big[0]['reference']['preview'].startswith('EMAIL')
    assert {'short one', 'another short one'} <= {i.get('content') for i in p['instructions']}


def test_practice_139_small_tasks_are_unchanged(conn):
    root = say(conn, 'Chat with JD')
    task = hb_tasks.bind(conn, 7, root, title='Chat with JD', studio=False)
    for text in ['first', 'second']:
        hb_tasks.bind(conn, 7, say(conn, text), task_id=task['task_id'])
    p = hb_tasks.packet(conn, hb_tasks.get(conn, task['task_id']))
    assert [i['content'] for i in p['instructions']] == ['first', 'second']
