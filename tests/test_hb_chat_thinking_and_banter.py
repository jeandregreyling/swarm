"""Direct main-chat APEX turns require live thought and answer casual banter naturally without KC tangents."""
from pathlib import Path
import sqlite3

from core import apex_tools, hb_owner_intent, hb_tasks

ROOT = Path(__file__).resolve().parents[1]


def test_inline_chat_requires_thought_while_default_stays_compatible():
    fmt = apex_tools.response_format_for_turn(require_thought=True)
    for branch in fmt['json_schema']['schema']['oneOf']:
        assert 'thought' in branch['required']
    chat_src = (ROOT / 'frontend/blueprints/chat.py').read_text(encoding='utf-8')
    assert 'response_format_for_turn(require_thought=True' in chat_src


def test_casual_banter_card_tells_apex_not_to_search_kc():
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, '
        'from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)'
    )
    hb_tasks.ensure_schema(conn)
    mid = conn.execute(
        "INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
        "VALUES (2845,'user','apex','Hey apex how is your new can do attitude feeling?','chat',0)"
    ).lastrowid
    task = hb_owner_intent.chat_task(conn, 2845, mid)
    card_text = hb_owner_intent.card(conn, task, kind='remark')
    assert 'do NOT run knowledge_search on casual banter' in card_text
