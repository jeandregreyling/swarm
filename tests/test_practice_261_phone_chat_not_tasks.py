"""Practice 261: phone chatter is chat, real requests are tasks."""
import sqlite3

from core import hb_tasks


def _db(text):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, content TEXT, from_agent TEXT)')
    c.execute('CREATE TABLE hb_channel_log(message_id INT, direction TEXT, channel TEXT)')
    c.execute("INSERT INTO messages VALUES (1, ?, 'user')", ('📱 Telegram: ' + text,))
    c.execute("INSERT INTO hb_channel_log VALUES (1, 'in', 'telegram')")
    return c


def test_chatter_go_aheads_and_follow_ups_are_chat():
    for t in ("Hurry up and answer me, what's your next task and can you do it", 'Build it Apex', 'Test this you dummy',
              'Thanks Claude you asshole now do your tasks Apex', 'Is it too much to ask you fuckers do work through the fucking task list'):
        assert hb_tasks._channel_feedback(_db(t), 1), t


def test_a_real_request_is_still_work():
    t = 'Write a one page brief on BHP contract awards this year with sources and send it to me'
    assert not hb_tasks._channel_feedback(_db(t), 1)
