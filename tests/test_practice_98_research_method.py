"""Practice 98 (owner 16 Nov 2026): "make sure HB knows how to do research properly". A research task or question now carries HB's
research method on APEX's clipboard: Knowledge Centre first, read, cite KC ids / note numbers, newest wins, follow references, say what
is unknown. Other work does not get it."""
from core import hb_learning, hb_owner_intent


def test_practice_98_the_method():
    m = hb_learning.research_method()
    assert m.startswith('Research method (follow it): (1) Knowledge Centre first')
    for must in ('knowledge_search', 'knowledge_read', 'SAP Note <number>', '/notes follow PY-AU', 'still unknown', 'credentials'):
        assert must in m


def test_practice_98_only_research_gets_it():
    assert 'research' in hb_learning.skills_for_text('What does SAP say about STP Phase 2 for Australian payroll?')
    assert 'research' not in hb_learning.skills_for_text('fix the layout code in core/hb_layout.py')


def test_practice_98_chat_card_carries_the_method_for_a_research_question(monkeypatch):
    import sqlite3
    from core import hb_queue
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, content TEXT)')
    c.execute('CREATE TABLE hb_task_messages(task_id TEXT, message_id INT)')
    monkeypatch.setattr(hb_queue, 'summary', lambda conn, cid: 'nothing running')
    monkeypatch.setattr(hb_queue, 'status', lambda conn: {'items': []})
    task = {'task_id': 'T-1', 'conversation_id': 2845}
    for text, expect in (('Explain how SAP payroll calculates Australian super guarantee', True), ('thanks, looks good', False)):
        c.execute('DELETE FROM messages'); c.execute('DELETE FROM hb_task_messages')
        mid = c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', ?)", (text,)).lastrowid
        c.execute("INSERT INTO hb_task_messages VALUES ('T-1', ?)", (mid,))
        assert ('Research method (follow it)' in hb_owner_intent.card(c, task)) is expect, text
