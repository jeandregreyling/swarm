"""Prepare the bounded fix for JD's 20 Nov instruction to clear the task list."""
import subprocess
from pathlib import Path
from core import hb_change_sets as cs

STEP = 'S-6E6EA42ED2'
TEST_PATH = 'tests/test_hb_clear_task_list_intent.py'
TEST = '''import pytest

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
'''

edits = [
    {'path': 'core/hb_owner_intent.py',
     'old': 'def classify(text):',
     'new': '''_CLEAR_EXISTING = re.compile(
    r"(?:(?:^|[.!?\\n]\\s*)(?:please\\s+|you (?:need|have) to\\s+|(?:can|could|would) you\\s+(?:please\\s+)?)?"
    r"|(?<!\\w)@(?:apex|hb|hummingbird)[,:]?\\s+you (?:need|have) to\\s+)"
    r"clear (?:(?:the|your|all|open|remaining)\\s+)*(?:task list|tasks|backlog)"
    r"(?=\\s*(?:$|[.!?,;]|\\b(?:and|then|so)\\b))", re.I)


def clear_task_list_request(text):
    """A direct go-ahead to finish existing work; questions about clearing a backlog are research."""
    body = _FILLER.sub('', str(text or '')).strip()
    return len(body.split()) <= 80 and not _CONCRETE.search(body) and bool(_CLEAR_EXISTING.search(body))


def classify(text):'''},
    {'path': 'core/hb_owner_intent.py',
     'old': "    if _DRIVE_WHOLE.match(body) or _DRIVE.search(body):",
     'new': "    if _DRIVE_WHOLE.match(body) or _DRIVE.search(body) or clear_task_list_request(body):"},
    {'path': 'core/apex_tools.py',
     'old': "    if t.lstrip().startswith('{'):\n        return False\n    # Practice 162",
     'new': "    if t.lstrip().startswith('{'):\n        return False\n    # Owner go-aheads drive the existing backlog even when they mention learning along the way.\n    from core.hb_owner_intent import clear_task_list_request\n    if clear_task_list_request(t):\n        return False\n    # Practice 162"},
]

path = Path(TEST_PATH)
assert not path.exists(), 'Refuse to overwrite an existing test'
path.write_text(TEST)
try:
    before = subprocess.run(['.venv/bin/python', '-m', 'pytest', '-q', '-o', 'addopts=', TEST_PATH],
                            capture_output=True, text=True)
    print('BEFORE:', before.stdout[-4000:])
    assert before.returncode == 1, 'The regression must fail before the fix'
finally:
    path.unlink()

out = cs.prepare(STEP, why='Main-chat message 18498 asked APEX to clear its existing task list and learn along the way. It became new work and SAP research because clear was missing from the drive pattern and learn triggered research. Recognise only direct instructions to clear existing work and exclude those from research review; preserve SAP status questions, questions about clearing backlogs, negation, and concrete new requests.',
                 edits=edits, new_files={TEST_PATH: TEST},
                 test={'tests': [TEST_PATH, 'tests/test_hb_owner_intent_and_queue.py',
                                  'tests/test_practice_128_research_checks.py', 'tests/test_practice_160_review_before_assigning.py',
                                  'tests/test_practice_162_suite_fixes.py']}, prepared_by='codex-instructor')
print('PREPARED:', out['verified'])
