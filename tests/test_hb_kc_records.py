import json
import sqlite3

import pytest

from core import hb_kc_records as kc, hb_tasks


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE conversations(id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT,
                              message_type TEXT, tokens_used INT, created_at TEXT DEFAULT '2026-11-12 08:00:00');
        CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'text',
            source_ref TEXT, raw_text TEXT, domain_tags TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'active',
            added_by TEXT NOT NULL DEFAULT 'ghost', chunk_count INTEGER NOT NULL DEFAULT 0, created_at DATETIME DEFAULT (datetime('now')),
            updated_at DATETIME DEFAULT (datetime('now')), category TEXT NOT NULL DEFAULT 'general', subcategory TEXT, content_hash TEXT);
        CREATE TABLE knowledge_chunks(chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INT, chunk_index INT, chunk_text TEXT,
            embedding TEXT, created_at DATETIME DEFAULT (datetime('now')));
        INSERT INTO conversations VALUES (2834, 'Main chat');
    """)
    hb_tasks.ensure_schema(c)
    yield c
    c.close()


def say(c, sender, text, mtype='chat', to='apex', conv=2834):
    return c.execute('INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES(?,?,?,?,?,0)',
                     (conv, sender, to, text, mtype)).lastrowid


def test_every_chat_message_is_saved_in_kc_with_findable_headers(conn):
    first = say(conn, 'user', 'Please build the sundial switches')
    say(conn, 'apex', 'I read core/sundial.py first', to='user')
    assert kc.index_chats(conn) == 2
    src = conn.execute("SELECT source_id, title, raw_text, domain_tags, source_ref, chunk_count FROM knowledge_sources").fetchone()
    assert src['title'].startswith('HB chat #2834 (chat:2834): Main chat') and src['source_ref'] == 'hb-chat:2834'
    assert f'[chat:2834 #{first} ' in src['raw_text'] and 'Please build the sundial switches' in src['raw_text']
    assert 'chat:2834' in json.loads(src['domain_tags']) and src['chunk_count'] >= 1
    assert kc.index_chats(conn) == 0                                         # nothing new


def test_new_messages_are_appended_not_rewritten(conn):
    say(conn, 'user', 'one ' * 30)
    kc.index_chats(conn)
    before = conn.execute('SELECT source_id, chunk_count FROM knowledge_sources').fetchone()
    late = say(conn, 'user', 'a later message about vram ' * 10)
    assert kc.index_chats(conn) == 1
    after = conn.execute('SELECT source_id, raw_text, chunk_count FROM knowledge_sources').fetchone()
    assert after['source_id'] == before['source_id'] and f'#{late} ' in after['raw_text']
    assert after['chunk_count'] > before['chunk_count']
    indexes = [r[0] for r in conn.execute('SELECT chunk_index FROM knowledge_chunks WHERE source_id=? ORDER BY chunk_index', (after['source_id'],))]
    assert indexes == list(range(len(indexes)))                             # appended chunks continue the sequence


def test_machine_traffic_is_capped_with_a_pointer_to_the_original(conn):
    mid = say(conn, 'apex', 'x' * 5000, mtype='tool_result')
    kc.index_chats(conn)
    text = conn.execute('SELECT raw_text FROM knowledge_sources').fetchone()[0]
    assert f'more characters in chat message #{mid}]' in text and 'x' * 5000 not in text


def test_batch_limit_spreads_backfill_over_ticks(conn):
    for i in range(7):
        say(conn, 'user', f'message {i} ' * 10)
    assert kc.index_chats(conn, limit=3) == 3
    assert kc.index_chats(conn, limit=3) == 3
    assert kc.index_chats(conn, limit=3) == 1
    text = conn.execute('SELECT raw_text FROM knowledge_sources').fetchone()[0]
    assert all(f'message {i} ' in text for i in range(7))


def test_task_record_is_written_tagged_and_refreshed(conn):
    mid = say(conn, 'user', 'Fix the sundial so it shows real VRAM')
    task = hb_tasks.bind(conn, 2834, mid)
    hb_tasks.event(conn, task, 'apex', 'task_plan', {'next_action': 'Read /sys/class/drm/card1/device/mem_info_vram_used'})
    say(conn, 'apex', 'Plan saved', to='user')
    written = kc.index_tasks(conn)
    assert task['task_id'] in written
    rec = conn.execute("SELECT raw_text, domain_tags, title, source_ref FROM knowledge_sources WHERE source_ref=?",
                       ('hb-task:' + task['task_id'],)).fetchone()
    assert rec['title'].startswith('HB task ' + task['task_id'])
    assert 'Fix the sundial so it shows real VRAM' in rec['raw_text'] and 'mem_info_vram_used' in rec['raw_text']
    assert 'chat:2834' in rec['raw_text'] and task['task_id'] in json.loads(rec['domain_tags'])
    assert kc.index_tasks(conn) == []                                        # unchanged task is not rewritten
    hb_tasks.event(conn, task, 'apex', 'test_result', {'alm_run_status': 'pass', 'verdict': 'PASS: 3 passed'})
    assert kc.index_tasks(conn) == [task['task_id']]
    rec = conn.execute("SELECT raw_text FROM knowledge_sources WHERE source_ref=?", ('hb-task:' + task['task_id'],)).fetchone()
    assert 'PASS: 3 passed' in rec['raw_text']
    assert conn.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_ref=?", ('hb-task:' + task['task_id'],)).fetchone()[0] == 1


def test_pointer_names_the_documents_compaction_can_return_to(conn):
    mid = say(conn, 'user', 'Remember this decision: keep the nanny bot in RAM')
    task = hb_tasks.bind(conn, 2834, mid)
    assert kc.pointer(conn, 2834, task['task_id']) is None                   # nothing indexed yet
    kc.tick(conn)
    ids = kc.document_ids(conn, 2834, task['task_id'])
    assert ids['chat']['document_id'] == kc.LIBRARY_ID + ids['chat']['source_id']
    text = kc.pointer(conn, 2834, task['task_id'])
    assert str(ids['task']['document_id']) in text and str(ids['chat']['document_id']) in text
    assert "knowledge_search 'chat:2834'" in text and 'knowledge_read' in text
