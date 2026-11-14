"""Learning step 0: verified past work becomes worked examples on the DREAM clipboard."""
import json
import sqlite3

import pytest

from core import hb_tasks, hb_learning as learning, hb_dream_method as dream


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT,'
              ' message_type TEXT, tokens_used INT, created_at TEXT)')
    hb_tasks.ensure_schema(c)
    yield c
    c.close()


def task(c, text, state='active'):
    mid = c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'user','apex',?,'chat')", (text,)).lastrowid
    t = hb_tasks.bind(c, 1, mid)
    c.execute('UPDATE hb_tasks SET state=? WHERE task_id=?', (state, t['task_id']))
    return hb_tasks.get(c, t['task_id'])


def tool(c, t, name, status='succeeded'):
    hb_tasks.event(c, t, 'apex', 'tool_result', {'tool': name, 'status': status, 'output': '...'})


def check(c, t, ok, verdict='PASS: 3 passed'):
    hb_tasks.event(c, t, 'apex', 'test_result', {'alm_run_status': 'pass' if ok else 'fail', 'verdict': verdict})


def test_only_verified_tasks_become_examples_using_the_final_verified_segment(conn):
    good = task(conn, 'Fix the sundial VRAM gauge')
    tool(conn, good, 'grep_repo'); check(conn, good, False, 'FAIL'); tool(conn, good, 'read_file'); tool(conn, good, 'read_file')
    check(conn, good, True, 'PASS: 4 passed')
    unverified = task(conn, 'Fix the sundial GPU gauge')
    tool(conn, unverified, 'read_file')
    assert learning.verified_task_ids(conn) == {good['task_id']}
    ex = learning.worked_example(conn, good['task_id'])
    assert ex['steps'] == 'read_file x2 -> run_tests (PASS)'             # the path after the failed check only
    assert ex['verdict'] == 'PASS: 4 passed' and 'wrapper' in ex['skills']


def test_accepted_tasks_count_and_meandering_paths_are_not_examples(conn):
    accepted = task(conn, 'Research SAP payroll schema AU01', state='completed')
    tool(conn, accepted, 'knowledge_search'); tool(conn, accepted, 'knowledge_read')
    flail = task(conn, 'Research SAP payroll clusters')
    for _ in range(30):
        tool(conn, flail, 'knowledge_search')
    check(conn, flail, True)
    new = task(conn, 'Look up how SAP payroll schema works')
    picked = learning.examples_for(conn, new)
    assert [e['task_id'] for e in picked] == [accepted['task_id']]
    assert 'research' in picked[0]['skills'] and picked[0]['verdict'] == 'accepted'


def test_examples_appear_on_the_dream_clipboard(conn):
    done = task(conn, 'Remember what we decided about the nanny bot', state='completed')
    tool(conn, done, 'task_evidence'); tool(conn, done, 'memory_search')
    new = task(conn, 'What did we decide earlier about the nanny bot placement?')
    card = dream.card(conn, new)
    assert 'Worked examples from verified past work' in card and done['task_id'] in card
    assert 'task_evidence -> memory_search' in card


def test_dataset_export_keeps_provenance(conn, tmp_path):
    done = task(conn, 'Read core/x.py and report the constant', state='completed')
    tool(conn, done, 'read_file')
    path = tmp_path / 'dataset.jsonl'
    assert learning.export_dataset(conn, path) == 1
    row = json.loads(path.read_text().splitlines()[0])
    assert row['task_id'] == done['task_id'] and row['tool_steps'] == 'read_file' and 'verified' in row['provenance']


def test_paused_or_failure_ending_tasks_are_not_verified_even_with_a_pass(conn):
    looped = task(conn, 'Continue the DREAM build')
    tool(conn, looped, 'read_file'); check(conn, looped, True)
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'apex','user',"
                 "'Attached apex request did not complete: RuntimeError: read_file failed','chat')")
    hb_tasks.bind(conn, 1, conn.execute('SELECT MAX(id) FROM messages').fetchone()[0], task_id=looped['task_id'], kind='reply')
    paused = task(conn, 'Help APEX finish the build', state='paused')
    tool(conn, paused, 'read_file'); check(conn, paused, True)
    good = task(conn, 'Verify the kernel')
    tool(conn, good, 'run_tests'); check(conn, good, True)
    assert learning.verified_task_ids(conn) == {good['task_id']}
