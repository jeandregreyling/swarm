"""Owner, 14 Nov 2026: when Codex is switched off or out of quota, the attached VS Code
instructor (copilot-instructor, whose link polls the peer bridge) takes independent review
instead of parking without a reviewer. Living-plan code then waits for the owner's
separate approval; isolated-component grants retain their existing acceptance flow."""
import time
import json
from contextlib import closing

import pytest

from core import hb_tasks, peer_bridge as peers, hb_task_manager as manager
from test_agent_identity import api, enrolled, headers, connect
from test_hb_task_api import assigned, invoke
from test_hb_task_api import test_independent_acceptance_automatically_queues_only_authorized_runtime_activation as _isolated_runtime_acceptance
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



@pytest.mark.usefixtures("owner_turned_continuation_on", "online_providers_authorised", "owner_defined_done")
def test_authorized_isolated_runtime_acceptance_is_preserved(assigned, monkeypatch, tmp_path):
    _isolated_runtime_acceptance(assigned, monkeypatch, tmp_path)


@pytest.mark.parametrize('after_review', ['none', 'mutation', 'instruction', 'task_plan', 'failed_case'])
def test_living_plan_code_needs_current_qa_then_separate_owner_approval(assigned, monkeypatch, after_review):
    from core import hb_plan_workflow as wf, hb_commands as hc, hb_task_manager as manager, apex_test_runner, hb_change_sets
    client, root, path, rid, task = assigned
    monkeypatch.setattr(wf, 'DEFAULT_PROJECT', task['project_id'])
    monkeypatch.setattr(hb_change_sets, 'commit', lambda *_: {'state': 'no prepared changes'})
    monkeypatch.setattr(apex_test_runner, 'run_tests', lambda _: {
        'status': 'passed', 'exit_code': 0, 'summary': '1 passed', 'output_tail': '1 passed'})
    with closing(connect(path)) as conn, conn:
        hb_tasks.event(conn, task, 'user', 'continuation_control', {
            'mode': 'on', 'via': 'test', 'actor': 'fixture owner'})
        manager.register(conn, task, request_id=rid)
    changed = invoke(assigned, 'propose_patch', {
        'file_path': 'hello.py', 'exact_old_text': 'hello', 'new_text': 'hello\n# scoped correction'})
    assert changed.status_code == 200, changed.get_json()
    tested = invoke(assigned, 'run_tests', {'tests': ['tests/test_hb_task_api.py']})
    assert tested.status_code == 200, tested.get_json()
    answer = client.post('/api/peer/v1/messages', headers=headers('apex'), json={
        'conversation_id': 1, 'text': 'Applied the assigned change and saved the guarded check',
        'reply_to_request_id': rid, 'route_reply': False}).get_json()
    with closing(connect(path)) as conn, conn:
        assert not any(i['key'] == f"accept:{task['step_id']}" for i in hc.waiting_items(conn))
        assert 'QA' in hc.accept_step(conn, task['step_id'], 'fixture owner')
        assert hb_tasks.get(conn, task['task_id'])['state'] == 'active'
        mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'hummingbird','Review source and guarded evidence')").lastrowid
        hb_tasks.bind(conn, 1, mid, task_id=task['task_id'], kind='checkpoint')
        review = peers.enqueue(conn, 1, mid, 'Review source and guarded evidence', ['codex-instructor'], sender='hummingbird')[0]
    reviewed = client.post('/api/agent/v1/tools', headers=headers('codex-instructor'), json={
        'tool': 'studio_accept', 'arguments': {'evidence_message_ids': [answer['message_id']]},
        'context': {'request_id': review, 'model': 'actual-instructor'}})
    assert reviewed.status_code == 200, reviewed.get_json()
    result = json.loads(reviewed.get_json()['output'])
    assert result['state'] == 'awaiting_owner' and result['alm_run_id']
    assert 'runtime_activation' not in result
    with closing(connect(path)) as conn, conn:
        assert hb_tasks.get(conn, task['task_id'])['state'] == 'active'
        assert conn.execute('SELECT status FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone()[0] != 'done'
        assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE task_id=? AND kind='accepted'", (task['task_id'],)).fetchone()[0] == 0
        assert any(i['key'] == f"accept:{task['step_id']}" for i in hc.waiting_items(conn))
        if after_review != 'none':
            if after_review == 'failed_case':
                conn.execute("UPDATE project_test_cases SET status='failed' WHERE step_id=?", (task['step_id'],))
            else:
                hb_tasks.event(conn, task, 'apex', after_review, {'content': 'The verified task changed'})
            assert not any(i['key'] == f"accept:{task['step_id']}" for i in hc.waiting_items(conn))
            assert 'Cannot approve' in hc.accept_step(conn, task['step_id'], 'fixture owner')
            assert hb_tasks.get(conn, task['task_id'])['state'] == 'active'
        else:
            conn.execute("UPDATE hb_peer_work SET state='completed'")
            conn.execute("UPDATE hb_tasks SET objective=? WHERE task_id=?",
                         ('Done when: python -m pytest tests/test_hb_task_api.py passes', task['task_id']))
            manager.register(conn, hb_tasks.get(conn, task['task_id']))
            assert manager.tick(conn) == []
            assert conn.execute('SELECT state FROM hb_task_manager WHERE task_id=?', (task['task_id'],)).fetchone()[0] == 'needs_owner'
            assert 'You approved it' in hc.accept_step(conn, task['step_id'], 'fixture owner')
            assert hb_tasks.get(conn, task['task_id'])['state'] == 'completed'
