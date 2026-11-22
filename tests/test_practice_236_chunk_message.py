"""Practice 236 (S-EEC7B9D03E): one living chat message per task run updated in place as chunks finish."""
import importlib
import sqlite3

from core import hb_chunk_message as cm


def test_import_hb_chunk_message():
    assert importlib.import_module('core.hb_chunk_message') is cm


def test_living_chunk_message_creates_once_and_updates_in_place():
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, '
        'from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)'
    )
    task = {'task_id': 'T-CHUNK0000001', 'conversation_id': 2845, 'title': 'Chunk test task'}
    chunks_v1 = [
        {'n': 1, 'text': 'read source', 'state': 'doing'},
        {'n': 2, 'text': 'patch file', 'state': 'todo'},
    ]
    mid1 = cm.upsert(conn, task, chunks_v1)
    chunks_v2 = [
        {'n': 1, 'text': 'read source', 'state': 'done'},
        {'n': 2, 'text': 'patch file', 'state': 'doing'},
    ]
    mid2 = cm.upsert(conn, task, chunks_v2)
    assert mid1 == mid2
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
    content = conn.execute('SELECT content FROM messages WHERE id=?', (mid1,)).fetchone()[0]
    assert '1/2 chunks done' in content and '✓ 1. read source' in content and '▶ 2. patch file' in content

