"""Owner 14 Nov: "never answer a question with a question unless it has a different outcome than expected - worth measuring and learning"."""
from core import hb_tasks, hb_merits, hb_question_check as qc
from test_peer_turns import flow, reply, owner  # noqa: F401


def test_what_counts_as_answering_with_a_question():
    assert qc.is_question('Could you define the done criteria for this task?')
    assert qc.is_question('Which file do you mean? The rename tool or the test?')
    assert qc.is_question('What exactly should be done? Please define the done criteria.')        # a request back to JD counts too
    assert not qc.is_question('The IP address is 10.0.0.8.')
    assert not qc.is_question('I renamed the file. Should I also update the docs? I will do that next.')   # mostly an answer


def test_an_unneeded_question_is_a_lesson_and_a_needed_one_counts_for_the_agent(flow):
    conn, p = flow
    rid = owner(conn, 'apex')
    reply(conn, p['apex'], rid, 'What exactly should be done? Please define the done criteria.')
    assert qc.resolve(conn, 1, 'just do it') == 'unneeded'
    lesson = conn.execute("SELECT note FROM hb_merits WHERE kind='lesson'").fetchone()[0]
    assert "a question that changed nothing" in lesson and "the assumption you made" in lesson
    rid2 = owner(conn, 'apex')
    reply(conn, p['apex'], rid2, 'Do you want the 32B or the 46B model for this?')
    assert qc.resolve(conn, 1, 'the 46B one, and keep the 24B as backup for the night runs') == 'needed'
    prof = {x['role']: x for x in hb_merits.profile(conn)}['APEX']
    assert prof['asked_needed'] == 1 and prof['asked_unneeded'] == 1
    assert 'questions back: 1 needed / 1 unneeded' in hb_merits.status_text(conn)
    assert qc.resolve(conn, 1, 'thanks') is None                                   # nothing open any more


def test_questions_to_hbs_own_requests_are_not_counted(flow):
    conn, p = flow
    rid = owner(conn, 'apex')
    task = hb_tasks.for_request(conn, rid)
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'hummingbird','apex','go on','checkpoint')").lastrowid
    hb_tasks.bind(conn, 1, mid, task_id=task['task_id'], kind='checkpoint')
    from core import peer_bridge
    auto = peer_bridge.enqueue(conn, 1, mid, 'continue the task', ['apex'], sender='hummingbird')[0]
    reply(conn, p['apex'], auto, 'Should I run the tests?')
    assert not conn.execute("SELECT 1 FROM hb_task_events WHERE kind='asked_back'").fetchone()
