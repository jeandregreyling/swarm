import pytest

from core import hb_apex_swap, hb_owner_intent, hb_queue, hb_tasks
from core.apex_tools import research_question
from test_peer_turns import flow  # noqa: F401
from test_hb_plan_workflow import plan, P  # noqa: F401


OWNER_MESSAGE = ("I'm not going to keep asking you to make these decicions @APEX you need to clear your task list "
                 "and do learn a few things along the way and be amazing, show the online models what you can do")


@pytest.mark.parametrize('text', [OWNER_MESSAGE, 'clear your task list', '@apex please clear the backlog',
                                'Clear the open tasks and learn from the results'])
def test_clear_existing_work_drives_queue_and_is_not_research(text):
    assert hb_owner_intent.classify(text) == 'drive'
    assert not research_question(text)


@pytest.mark.parametrize('text', ['Clear validation errors in core/api.py', 'Research SAP payroll wage types',
                                'Explain how payroll creates wage type /XQE', 'Create a new task list for the migration'])
def test_real_new_work_and_research_remain_new_requests(text):
    assert hb_owner_intent.classify(text) is None


@pytest.mark.parametrize('text', ['What does status 03 mean in SAP payroll?',
                                'Explain the payroll control record status in SAP',
                                'How do I clear the backlog in SAP workflow?',
                                'Can you research how to clear tasks in SAP workflow?',
                                'Can you clear tasks in SAP workflow?',
                                'Do not clear your task list; explain SAP payroll schemas.'])
def test_research_questions_and_negation_do_not_start_the_queue(text):
    assert hb_owner_intent.classify(text) != 'drive'
    assert research_question(text)


@pytest.mark.parametrize('text', ['Do you need to clear your task list?',
                                "I don't think you need to clear your task list.",
                                'Explain why you need to clear your task list.',
                                'How does @APEX clear your task list?',
                                'If you need to clear your task list, ask me first.'])
def test_embedded_mention_is_not_permission_to_start_work(text):
    assert not hb_owner_intent.clear_task_list_request(text)
    assert hb_owner_intent.classify(text) != 'drive'


def test_owner_go_ahead_does_not_search_the_knowledge_centre():
    def unexpected_search(query):
        pytest.fail('queue-driving instruction must not launch a research search: ' + query)
    assert hb_apex_swap.review(OWNER_MESSAGE, search=unexpected_search)['kind'] == 'default'
    assert research_question('What is wage type /XQE and when does payroll create it?')


def test_go_ahead_joins_chat_and_starts_existing_plan_without_duplicate_step(plan):
    conn, _, _ = plan
    count = conn.execute('SELECT COUNT(*) FROM project_steps').fetchone()[0]
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) "
                       "VALUES(1,'user','apex',?,'chat')", (OWNER_MESSAGE,)).lastrowid
    assert hb_owner_intent.classify(OWNER_MESSAGE) == 'drive'
    task = hb_owner_intent.chat_task(conn, 1, mid)
    hb_queue.drive_on(conn, 'owner via chat go-ahead', 1, mid, project_id=P)
    assert task['step_id'] is None
    assert conn.execute('SELECT COUNT(*) FROM project_steps').fetchone()[0] == count
    workflow = __import__('core.hb_plan_workflow', fromlist=['settings']).settings(conn, P)
    assert workflow['enabled'] and workflow['task_id']
