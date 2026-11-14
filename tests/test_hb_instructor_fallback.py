"""Owner, 14 Nov 2026: when Codex is switched off or out of quota, the attached VS Code
instructor (copilot-instructor, whose link polls the peer bridge) takes independent review
and acceptance instead of the task parking at needs_owner."""
import time

from core import hb_tasks, peer_bridge as peers, hb_task_manager as manager
from test_agent_identity import api, enrolled, headers, connect
from test_hb_task_api import assigned
from test_peer_turns import flow


def test_review_recipient(flow):
    conn, _ = flow
    from core import hb_online
    peers.issue_token(conn, 'copilot-instructor')
    # Codex off (never switched) and no live link: the reviewer stays Codex (the park message says why).
    assert manager.review_recipient(conn) == 'codex-instructor'
    # Attached link: the instructor token used the peer API just now, so it takes the review.
    conn.execute("UPDATE service_tokens SET last_used_at=? WHERE principal_id='copilot-instructor'", (time.time(),))
    assert manager.review_recipient(conn) == 'copilot-instructor'
    # A stale link does not count.
    conn.execute("UPDATE service_tokens SET last_used_at=? WHERE principal_id='copilot-instructor'", (time.time() - 3600,))
    assert manager.review_recipient(conn) == 'codex-instructor'
    # An owner-authorised, usable Codex wins again.
    conn.execute("UPDATE service_tokens SET last_used_at=? WHERE principal_id='copilot-instructor'", (time.time(),))
    hb_online.set_mode(conn, 'codex', 'on', 'test')
    assert manager.review_recipient(conn) == 'codex-instructor'


def _review_request(path, task):
    from contextlib import closing
    with closing(connect(path)) as conn, conn:
        # The owner switched this task On (otherwise its tools stay held by chat control).
        hb_tasks.event(conn, task, 'user', 'continuation_control', {'mode': 'on', 'via': 'test', 'actor': 'test'})
        mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'hummingbird','Independently review the component')").lastrowid
        hb_tasks.bind(conn, 1, mid, task_id=task['task_id'], kind='checkpoint')
        return peers.enqueue(conn, 1, mid, 'Review source and verification', ['copilot-instructor'], sender='hummingbird')[0]


def test_copilot_instructor_acceptance_reaches_the_evidence_check(assigned):
    client, _, path, _, task = assigned
    review = _review_request(path, task)
    response = client.post('/api/agent/v1/tools', headers=headers('copilot-instructor'), json={
        'tool': 'studio_accept', 'arguments': {'evidence_message_ids': [1]},
        'context': {'request_id': review, 'model': 'test'}})
    # Before this change the same call failed identity ("Independent acceptance belongs to the
    # authenticated instructor"). Passing the gate, bogus evidence fails on evidence instead.
    assert response.status_code == 403, response.get_json()
    assert 'Acceptance evidence must be an actual successful reply' in str(response.get_json())


def test_copilot_instructor_coaches_with_task_plan(assigned):
    client, _, path, _, task = assigned
    review = _review_request(path, task)
    text = 'Read core/hb_rename.py lines 1-40, apply the one exact correction named there, then run the step check.'
    response = client.post('/api/agent/v1/tools', headers=headers('copilot-instructor'), json={
        'tool': 'task_plan', 'arguments': {'next_action': text},
        'context': {'request_id': review, 'model': 'test'}})
    assert response.status_code == 200, response.get_json()
