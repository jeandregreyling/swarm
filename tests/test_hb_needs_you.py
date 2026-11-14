"""Owner 12 Nov: approvals "hover" at the top of main chat. Everything waiting for the owner, with what it points to."""
import sqlite3

import pytest

from core import hb_commands as hc, hb_tasks, hb_task_manager


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT,
                              message_type TEXT, tokens_used INT, created_at TEXT);
        CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT,
                                   order_idx INT, created_at REAL, updated_at REAL, residual_risk TEXT);
        CREATE TABLE peer_messages(id INTEGER PRIMARY KEY, conversation_id INT, message_id INT, sender TEXT, recipient TEXT,
                                   body TEXT, created_at REAL, delivered_at REAL);
        CREATE TABLE hb_peer_work(request_id INT, principal TEXT, state TEXT, stage TEXT, updated_at REAL);
    """)
    hb_tasks.ensure_schema(c)
    hb_task_manager.ensure_schema(c)
    hc.ensure_schema(c)
    yield c
    c.close()


def _task(c, tid, title, step=None, state='active', root=None):
    root = root or c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) "
                             "VALUES(2834,'hummingbird','apex',?,'instruction')", (f'Studio task {step}: {title}',)).lastrowid
    c.execute("INSERT INTO hb_tasks(task_id,conversation_id,root_message_id,title,objective,project_id,step_id,state,created_at,updated_at,version)"
              " VALUES(?,2834,?,?,?,?,?,?,0,0,1)", (tid, root, title, title, 'P-2AB8250A87' if step else None, step, state))
    return root


def _held(c, rid, tid, mid):
    c.execute("INSERT INTO peer_messages VALUES(?,2834,?,'apex','codex-instructor','Please review the diff',0,NULL)", (rid, mid))
    c.execute("INSERT INTO hb_peer_work VALUES(?,'codex-instructor','needs_review','Provider unavailable; review retained',0)", (rid,))
    if tid:
        c.execute('INSERT INTO hb_task_requests(task_id,request_id) VALUES(?,?)', (tid, rid))


@pytest.fixture
def waiting(conn):
    c = conn
    c.execute("INSERT INTO project_steps VALUES('S-D8CC58DE6D','P-2AB8250A87','Sundial: correct live hardware view','Built: GPU from sysfs; "
              "switches for RAM/VRAM.','partial','apex',8,0,5,'Built and tested; awaiting owner acceptance')")
    c.execute("INSERT INTO project_steps VALUES('S-0000000001','P-2AB8250A87','Not finished yet','','doing','apex',9,0,5,'')")
    sundial_root = _task(c, 'T-061F6516DC6C', 'S-D8CC58DE6D Sundial', 'S-D8CC58DE6D')
    _task(c, 'T-AAAAAAAAAAAA', 'Fix the GPU reading', 'S-0000000001')
    c.execute("INSERT INTO hb_task_manager(task_id,enabled,state,detail,next_due,updated_at) VALUES('T-AAAAAAAAAAAA',1,'needs_owner',"
              "'Stopped, not looping: 8 checkpoints since the last passing check',0,10)")
    ask = hb_task_manager.ask_owner(c, hb_tasks.get(c, 'T-AAAAAAAAAAAA'), 'Stopped T-AAAAAAAAAAAA instead of looping.',
                                    '/continue T-AAAAAAAAAAAA gives it a fresh try; /cancel T-AAAAAAAAAAAA drops it.')
    held_mid = c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) "
                         "VALUES(2834,'apex','codex-instructor','review please','chat')").lastrowid
    _held(c, 41, 'T-AAAAAAAAAAAA', held_mid)                  # open task: listed
    _task(c, 'T-CCCCCCCCCCCC', 'old idea', state='cancelled')
    _held(c, 42, 'T-CCCCCCCCCCCC', None)                      # cancelled task: never listed, HB closes it
    _held(c, 43, None, None)                                  # no task at all: not listed
    hc.handle(c, 2834, '/cancel T-AAAAAAAAAAAA', 'jd')       # HB asks /yes or /no
    confirm_mid = c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES"
                            "(2834,'hummingbird','user','Cancel T-AAAAAAAAAAAA \"Fix the GPU reading\"? ... Reply /yes or /no.','response')").lastrowid
    return {'sundial_root': sundial_root, 'ask': ask, 'held_mid': held_mid, 'confirm_mid': confirm_mid}


def test_everything_waiting_is_listed_once_with_what_it_points_to(conn, waiting):
    items = hc.waiting_items(conn, 2834)
    assert [i['kind'] for i in items] == ['confirm', 'halted', 'review', 'accept']       # most urgent first
    confirm, halted, review, accept = items
    assert confirm['title'] == '/cancel T-AAAAAAAAAAAA' and [a['command'] for a in confirm['actions']] == ['/yes', '/no']
    assert confirm['message_ids'] == [waiting['confirm_mid']] and 'Fix the GPU reading' in confirm['detail']
    assert halted['task_id'] == 'T-AAAAAAAAAAAA' and halted['message_ids'] == [waiting['ask']]
    assert 'Stopped T-AAAAAAAAAAAA' in halted['detail'] and '\nDetails: task T-AAAAAAAAAAAA' in halted['detail']
    assert [(a['label'], a['command']) for a in halted['actions']] == [('Keep working', '/continue T-AAAAAAAAAAAA'),
                                                                       ('Cancel task…', '/cancel T-AAAAAAAAAAAA')]
    assert halted['open'] == {'type': 'step', 'id': 'S-0000000001'}                    # click opens its Studio step
    assert review['request_id'] == 41 and review['message_ids'] == [waiting['held_mid']]
    assert review['open'] == {'type': 'message', 'id': waiting['held_mid'], 'conversation_id': 2834}
    assert accept['label'] == 'Sundial' and accept['step_id'] == 'S-D8CC58DE6D'
    assert accept['detail'].startswith('Built: GPU from sysfs') and accept['why'].startswith('Built and tested')
    assert accept['message_ids'] == [waiting['sundial_root']] and accept['open'] == {'type': 'step', 'id': 'S-D8CC58DE6D'}
    assert [a['decision'] for a in accept['actions']] == ['accept', 'reject']
    assert not any(i.get('request_id') in (42, 43) for i in items)                      # dead requests never shown


def test_approvals_command_prints_the_same_list(conn, waiting):
    text = hc.handle(conn, 2834, '/approvals', 'jd')
    assert '/yes or /no on: /cancel T-AAAAAAAAAAAA' in text
    assert 'T-AAAAAAAAAAAA is halted' in text and '/continue T-AAAAAAAAAAAA or /cancel T-AAAAAAAAAAAA' in text
    assert 'request #41' in text and 'request #42' not in text and 'request #43' not in text
    assert '/accept S-D8CC58DE6D' in text


def test_other_chats_see_steps_and_halts_but_not_this_chats_yes_no(conn, waiting):
    kinds = [i['kind'] for i in hc.waiting_items(conn, 9999)]
    assert kinds == ['halted', 'review', 'accept']


def test_accepted_step_leaves_the_bar(conn, waiting):
    hc.accept_step(conn, 'S-D8CC58DE6D', 'jd')
    assert 'accept' not in [i['kind'] for i in hc.waiting_items(conn, 2834)]


def test_hb_closes_held_requests_of_finished_tasks_only(conn, waiting):
    assert hc.close_finished_reviews(conn) == 1
    states = dict(conn.execute('SELECT request_id, state FROM hb_peer_work').fetchall())
    assert states == {41: 'needs_review', 42: 'cancelled', 43: 'needs_review'}
    assert conn.execute('SELECT stage FROM hb_peer_work WHERE request_id=42').fetchone()[0] == 'Closed by HB: its task is cancelled'
    assert hc.close_finished_reviews(conn) == 0


def test_short_labels():
    assert hc._short('Main chat controls: approvals button, visible proposals') == 'Main chat controls'
    assert hc._short('Close Studio steps automatically when HB tasks finish') == 'Close Studio steps automatically when H…'
    assert hc._ask_actions('/online codex on authorises Codex reviews; /pause T-ABCDEF012345 holds it') == [
        {'label': 'Allow Codex', 'command': '/online codex on', 'fill': False},
        {'label': 'Pause', 'command': '/pause T-ABCDEF012345', 'fill': False}]
    assert hc._ask_actions('/done T-ABCDEF012345 <what must be true>')[0] == {'label': 'Say what done means…',
                                                                             'command': '/done T-ABCDEF012345 ', 'fill': True}


def test_finished_work_reaches_the_bar_even_when_held(conn):
    """Owner 13 Nov: practice 9 passed its tests, but the workflow was switched off first, so no Approve ever appeared."""
    import json
    conn.execute("INSERT INTO project_steps VALUES('S-45B4B76E22','P-2AB8250A87','Practice 9: grip','d','todo','apex',1,0,0,NULL)")
    conn.execute("INSERT INTO project_steps VALUES('S-0000000001','P-2AB8250A87','Unfinished','d','todo','apex',2,0,0,NULL)")
    _task(conn, 'T-0E892A1C612E', 'Practice 9', 'S-45B4B76E22')
    _task(conn, 'T-000000000001', 'Unfinished', 'S-0000000001')
    for tid, kind, payload, at in [('T-0E892A1C612E', 'mutation', {}, 10), ('T-0E892A1C612E', 'test_result', {'alm_run_status': 'pass'}, 20),
                                   ('T-000000000001', 'test_result', {'alm_run_status': 'pass'}, 10), ('T-000000000001', 'mutation', {}, 20)]:
        conn.execute("INSERT INTO hb_task_events(task_id,agent,kind,payload,created_at) VALUES(?,?,?,?,?)", (tid, 'apex', kind, json.dumps(payload), at))
    items = [i for i in hc.waiting_items(conn, 2834) if i['kind'] == 'accept']
    assert [i['step_id'] for i in items] == ['S-45B4B76E22']
    assert items[0]['why'].startswith('Finished') and items[0]['actions'][0]['decision'] == 'accept'


def test_finished_task_is_listed_once_not_as_halted_and_review_too(conn):
    """13 Nov: practice 10 showed as halted, review (a turn cut off by a restart) and accept at once."""
    import json
    conn.execute("INSERT INTO project_steps VALUES('S-CB6C8B566A','P-2AB8250A87','Practice 10: grip','d','todo','apex',1,0,0,NULL)")
    mid = _task(conn, 'T-6D17DCB3231B', 'Practice 10', 'S-CB6C8B566A')
    for kind, payload, at in [('mutation', {}, 10), ('test_result', {'alm_run_status': 'pass'}, 20)]:
        conn.execute("INSERT INTO hb_task_events(task_id,agent,kind,payload,created_at) VALUES('T-6D17DCB3231B','apex',?,?,?)",
                     (kind, json.dumps(payload), at))
    _held(conn, 501, 'T-6D17DCB3231B', mid)
    hb_task_manager.ask_owner(conn, hb_tasks.get(conn, 'T-6D17DCB3231B'), 'T-6D17DCB3231B is finished.', '/accept S-CB6C8B566A approves the step')
    kinds = [i['kind'] for i in hc.waiting_items(conn, 2834) if i.get('task_id') == 'T-6D17DCB3231B' and i['kind'] != 'workflow']
    assert kinds == ['accept']


def test_turn_cut_off_by_a_restart_is_closed_once_a_later_turn_completed(conn):
    mid = _task(conn, 'T-6D17DCB3231B', 'Practice 10', 'S-CB6C8B566A')
    _held(conn, 501, 'T-6D17DCB3231B', mid)
    conn.execute("INSERT INTO peer_messages VALUES(502,2834,?,'hummingbird','apex','next turn',0,1)", (mid,))
    conn.execute("INSERT INTO hb_peer_work VALUES(502,'apex','completed','done',0)")
    conn.execute("INSERT INTO hb_task_requests(request_id,task_id) VALUES(502,'T-6D17DCB3231B')")
    assert hc.close_finished_reviews(conn) == 1
    assert conn.execute("SELECT state FROM hb_peer_work WHERE request_id=501").fetchone()[0] == 'cancelled'


def test_approve_records_what_was_approved_the_check_the_comment_and_next(conn):
    """Owner 13 Nov: /accept in the chat should say what was approved and what happens next, and keep an optional comment."""
    import json
    conn.execute("INSERT INTO project_steps VALUES('S-CB6C8B566A','P-2AB8250A87','Practice 10: grip',"
                 "'Do: x\nDone when: the grip test passes\nDone when: only chat.css changed','todo','apex',1,0,0,NULL)")
    _task(conn, 'T-6D17DCB3231B', 'Practice 10', 'S-CB6C8B566A')
    conn.execute("INSERT INTO hb_task_events(task_id,agent,kind,payload,created_at) VALUES('T-6D17DCB3231B','apex','test_result',?,1)",
                 (json.dumps({'alm_run_status': 'pass', 'verdict': 'PASS: 1 passed'}),))
    text = hc.handle(conn, 2834, '/accept S-CB6C8B566A looks good, make the grip a bit wider later', 'jd')
    assert text.startswith('✅ Done: Practice 10: grip.\nYou approved it.')
    assert 'done when: the grip test passes; only chat.css changed' in text and 'check: PASS: 1 passed' in text
    assert 'step S-CB6C8B566A' in text and 'task T-6D17DCB3231B' in text
    assert 'Your comment is saved with it: looks good, make the grip a bit wider later' in text
    assert 'wider later' in conn.execute("SELECT residual_risk FROM project_steps WHERE step_id='S-CB6C8B566A'").fetchone()[0]
    assert json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE kind='owner_accepted'").fetchone()[0])['comment'].startswith('looks good')


def test_cut_off_turn_of_a_task_waiting_for_dependencies_is_closed(conn):
    mid = _task(conn, 'T-5F5301CB8E11', 'Cleanup 2', 'S-01754DD9C9')
    _held(conn, 601, 'T-5F5301CB8E11', mid)
    hb_task_manager.register(conn, hb_tasks.get(conn, 'T-5F5301CB8E11'))
    conn.execute("UPDATE hb_task_manager SET state='waiting_dependencies' WHERE task_id='T-5F5301CB8E11'")
    assert hc.close_finished_reviews(conn) == 1
    assert [i for i in hc.waiting_items(conn, 2834) if i['kind'] == 'review'] == []
