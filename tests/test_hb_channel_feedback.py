"""Channel feedback stays in chat; real scoped work and owner holds are preserved."""
import pytest
from core import hb_tasks as tasks
from test_peer_turns import flow
from test_hb_tasks import studio

def channel_message(conn, text, direction='in'):
    conn.execute("CREATE TABLE IF NOT EXISTS hb_channel_log(channel TEXT,direction TEXT,message_id INTEGER)")
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) "
                       "VALUES(1,'user','hummingbird',?,'chat')", ('📱 Telegram: ' + text,)).lastrowid
    conn.execute("INSERT INTO hb_channel_log VALUES('telegram',?,?)", (direction, mid))
    return mid


def test_channel_feedback_handoff_uses_chat_not_a_new_studio_task(flow):
    from core.hb_owner_intent import is_chat_task
    conn, _ = flow
    studio(conn)
    root = channel_message(conn, 'Fix yourself')
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,content) "
                       "VALUES(1,'copilot-instructor','Use this verified correction')").lastrowid
    task = tasks.prepare(conn, 1, mid)
    assert task['root_message_id'] == root and is_chat_task(task)
    assert tasks.for_message(conn, mid)['task_id'] == task['task_id']
    assert conn.execute('SELECT COUNT(*) FROM project_steps').fetchone()[0] == 0
    assert tasks.prepare(conn, 1, mid)['task_id'] == task['task_id']


def test_channel_feedback_reconciliation_clears_false_needs_owner_and_preserves_evidence(flow):
    from core import hb_task_manager as manager
    from core.hb_owner_intent import is_chat_task
    conn, _ = flow
    studio(conn)
    root = channel_message(conn, 'Fix yourself')
    task = tasks.bind(conn, 1, root)
    manager.register(conn, task)
    conn.execute("UPDATE hb_task_manager SET state='needs_owner',detail='Needs a definition of done' WHERE task_id=?", (task['task_id'],))
    conn.execute("UPDATE hb_tasks SET state='needs_review' WHERE task_id=?", (task['task_id'],))
    assert tasks.reconcile_channel_feedback(conn) == [task['task_id']]
    fixed = tasks.get(conn, task['task_id'])
    assert is_chat_task(fixed) and fixed['state'] == 'active'
    assert tasks.for_message(conn, root)['task_id'] == task['task_id']
    assert conn.execute('SELECT status FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone()[0] == 'skipped'
    assert conn.execute('SELECT enabled,state FROM hb_task_manager WHERE task_id=?', (task['task_id'],)).fetchone() == (0, 'idle')
    assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE task_id=? AND kind='channel_feedback_reclassified'", (task['task_id'],)).fetchone()[0] == 1
    assert tasks.reconcile_channel_feedback(conn) == []


@pytest.mark.parametrize('protected', ['mutation', 'case', 'instruction', 'paused'])
def test_channel_feedback_reconciliation_preserves_actual_work_and_owner_holds(flow, protected):
    conn, _ = flow
    studio(conn)
    root = channel_message(conn, 'Fix yourself')
    task = tasks.bind(conn, 1, root)
    if protected == 'mutation':
        tasks.event(conn, task, 'apex', 'mutation', {'paths': ['core/example.py']})
    elif protected == 'case':
        conn.execute('CREATE TABLE project_test_cases(step_id TEXT)')
        conn.execute('INSERT INTO project_test_cases VALUES(?)', (task['step_id'],))
    elif protected == 'instruction':
        mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','Fix core/example.py')").lastrowid
        tasks.bind(conn, 1, mid, task_id=task['task_id'])
    else:
        conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?", (task['task_id'],))
    assert tasks.reconcile_channel_feedback(conn) == []
    assert tasks.get(conn, task['task_id'])['step_id'] == task['step_id']


def test_channel_feedback_detection_does_not_reclassify_concrete_work_or_unverified_prefixes(flow):
    conn, _ = flow
    studio(conn)
    for text, direction in [('Fix core/example.py', 'in'), ('Fix yourself', 'out')]:
        root = channel_message(conn, text, direction)
        mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'copilot-instructor','Scoped correction')").lastrowid
        task = tasks.prepare(conn, 1, mid)
        assert task['root_message_id'] == root and task['step_id'] is not None


pytestmark = pytest.mark.usefixtures("owner_turned_continuation_on")
