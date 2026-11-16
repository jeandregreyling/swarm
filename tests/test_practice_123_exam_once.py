"""Practice 123 (monitoring 17 Nov 2026, 06:12): copilot-instructor has two finished exams (14 Nov, 16 Nov). Each tick finished both and each
overwrote the agent's latest exam, so "passed HB's exam" was announced twice every ten minutes (147 lines) and the score flipped between
1.0 and 0.85. Only an agent's newest exam is finished, once."""
import json
import sqlite3

from core import hb_agents


def test_practice_123_two_finished_exams_announce_once():
    c = sqlite3.connect(':memory:')
    hb_agents.ensure_schema(c)
    c.execute("INSERT INTO hb_agents(agent_id, kind, profile, about) VALUES ('copilot-instructor', 'online', 'advisor', 'Copilot')")
    for exam_id, sent in (('X-OLD', 100.0), ('X-NEW', 200.0)):
        for test in ('programmer', 'tools', 'researcher', 'social'):
            c.execute('INSERT INTO hb_agent_exams(exam_id, agent_id, test, tag, sent_at, conversation_id, answer, passed, why, answered_at) '
                      "VALUES (?, 'copilot-instructor', ?, 't', ?, 2845, 'a', 1, 'ok', ?)", (exam_id, test, sent, sent + 5))
    said = []
    for _ in range(3):
        hb_agents.exam_tick(c, say=said.append, now=1000.0)
    assert len(said) == 1 and 'X-NEW' in said[0]
    assert json.loads(c.execute("SELECT exam FROM hb_agents WHERE agent_id='copilot-instructor'").fetchone()[0])['exam_id'] == 'X-NEW'
