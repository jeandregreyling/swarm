"""Owner 12 Nov: "I approved all of them but the workflows haven't actually kicked off".

HB runs the Studio plan one step at a time: APEX scopes the next ready step read-only, the owner approves the plan,
HB runs it, the owner approves the result, and HB starts the next step. Off until the owner starts it."""
import json

import pytest

from core import hb_commands as hc, hb_tasks, hb_task_manager as tm, hb_plan_workflow as wf, peer_turns
from core.hb_chat_controls import continuation
from test_peer_turns import flow, reply  # noqa: F401  (fixture)

P = 'P-2AB8250A87'
PROPOSAL = ('Found:\n- core/hb_learning.py exports verified examples (export_dataset)\n'
            '**Done when:**\n1. The dataset is re-exported after every verified task\n2. tests/test_hb_learning.py passes\n'
            'Plan:\n1. Read export_dataset\n2. Call it from the task manager when a task is accepted\n3. Add a test')


@pytest.fixture
def plan(flow):
    conn, principals = flow
    conn.executescript("""
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, name TEXT, description TEXT, methodology TEXT, status TEXT, owner TEXT,
                              created_at REAL, updated_at REAL);
        CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT,
                                   order_idx INT, created_at REAL, updated_at REAL, residual_risk TEXT);
        CREATE TABLE project_step_deps(step_id TEXT, depends_on TEXT, created_at REAL);
    """)
    conn.execute(f"INSERT INTO projects VALUES('{P}','Plan','','agile','active','jd',0,0)")
    rows = [('S-00000000A0', 'DOES', 'done', 'apex', 'Accepted by owner (jd) via /accept'),
            ('S-00000000A1', 'Learning L1: harvest verified examples', 'partial', 'apex', 'Dataset exported'),
            ('S-00000000A2', 'Learning L2: exam', 'partial', 'apex', 'Exam built'),
            ('S-00000000A3', 'Learning L3: LoRA', 'blocked', 'apex', 'Owner deferred spending'),
            ('S-00000000A4', 'Bugs register', 'doing', 'hummingbird', '20 open'),
            ('S-00000000A5', 'Agent identities', 'todo', 'apex', '')]
    for n, (sid, title, status, owner, note) in enumerate(rows):
        conn.execute('INSERT INTO project_steps VALUES(?,?,?,?,?,?,?,0,?,?)', (sid, P, title, f'Scope of {title}', status, owner, n, n, note))
    conn.execute("INSERT INTO project_step_deps VALUES('S-00000000A2','S-00000000A1',0)")
    hb_tasks.ensure_schema(conn)
    tm.ensure_schema(conn)
    tasks = {}
    for sid, title, status, owner, _ in rows[1:]:
        if owner != 'apex':
            continue
        mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) "
                           "VALUES(1,'hummingbird','apex',?,'chat')", (f'Studio task {sid}: {title}',)).lastrowid
        tasks[sid] = hb_tasks.bind(conn, 1, mid, title=f'{sid} {title}', objective=f'Studio step {sid}: {title}',
                                   project_id=P, step_id=sid)['task_id']
    yield conn, principals, tasks


def _request(conn, task_id):
    return conn.execute("SELECT r.request_id FROM hb_task_requests r WHERE r.task_id=? ORDER BY r.request_id DESC LIMIT 1",
                        (task_id,)).fetchone()[0]


def test_off_until_the_owner_starts_it_and_the_bar_asks(plan):
    conn, _, tasks = plan
    wf.tick(conn)
    assert not conn.execute("SELECT 1 FROM hb_task_manager").fetchone()                  # nothing runs by itself
    item = next(i for i in hc.waiting_items(conn, 1) if i['kind'] == 'workflow')
    assert item['step_id'] == 'S-00000000A1' and [a['command'] for a in item['actions']] == ['/workflow on', '/workflow off']
    assert 'S-00000000A3 (blocked: Owner deferred spending)' in item['detail']
    assert 'S-00000000A4 (not APEX work' in item['detail'] and 'S-00000000A2 (waits for S-00000000A1)' in item['detail']
    assert 'Not now' in [a['label'] for a in item['actions']]
    hc.handle(conn, 1, '/workflow off', 'jd')                                            # "Not now" is remembered...
    assert not [i for i in hc.waiting_items(conn, 1) if i['kind'] == 'workflow']
    conn.execute("UPDATE project_steps SET residual_risk='Accepted by owner (jd) via /accept', updated_at=? WHERE step_id='S-00000000A0'",
                 (wf.settings(conn)['decided_at'] + 1,))
    assert [i for i in hc.waiting_items(conn, 1) if i['kind'] == 'workflow']             # ...until the owner approves something


def test_start_scopes_the_next_step_read_only_under_the_owners_go_ahead(plan):
    conn, _, tasks = plan
    t1 = tasks['S-00000000A1']
    answer = hc.handle(conn, 1, '/workflow on', 'jd')
    assert answer.startswith('Workflow on.') and 'S-00000000A1' in answer
    w = wf.settings(conn, P)
    assert w['enabled'] == 1 and w['task_id'] == t1 and w['stage'] == 'planning'
    rid = _request(conn, t1)
    body = json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?', (rid,)).fetchone()[0])
    assert body['task_type'] == 'hb_managed_plan' and 'Done when:' in body['instruction']
    scope = json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE kind='tool_scope' AND request_id=?", (rid,)).fetchone()[0])
    assert scope['allowed_tools'] == wf.PLAN_TOOLS and 'propose_patch' not in scope['allowed_tools']   # read-only turn
    c = continuation(conn, hb_tasks.get(conn, t1))
    assert c['mode'] == 'on' and c['actor'] == 'jd via /workflow' and c['revision'] == 0
    assert peer_turns.ready(conn, rid)                                                   # HB's own request may run
    assert continuation(conn, hb_tasks.get(conn, tasks['S-00000000A5']))['mode'] == 'off'  # one step at a time
    hc.handle(conn, 1, '/workflow off', 'jd')
    assert not peer_turns.ready(conn, rid) and continuation(conn, hb_tasks.get(conn, t1))['mode'] == 'off'
    hc.handle(conn, 1, '/workflow on', 'jd')
    assert wf.settings(conn, P)['task_id'] == t1 and _request(conn, t1) == rid             # resumed, not queued twice
    status = next(i for i in hc.waiting_items(conn, 1) if i['kind'] == 'status')
    assert status['info'] and status['label'].startswith('APEX is scoping')


def test_apex_proposal_goes_to_the_owner_and_approval_runs_it_then_the_next_step_starts(plan):
    conn, principals, tasks = plan
    t1, t2 = tasks['S-00000000A1'], tasks['S-00000000A2']
    hc.handle(conn, 1, '/workflow on', 'jd')
    rid = _request(conn, t1)
    result = reply(conn, principals['apex'], rid, PROPOSAL)
    assert result['handoff']['queued'] == []                                             # HB, not the bridge, decides what next
    tm.tick(conn)
    wf.tick(conn)
    item = next(i for i in hc.waiting_items(conn, 1) if i['kind'] == 'plan')
    assert item['task_id'] == t1 and 'Done when:\n- The dataset is re-exported after every verified task' in item['detail']
    assert [(a['label'], a['command']) for a in item['actions']] == [
        ('Approve plan', f'/plan {t1}'), ('Write my own done…', f'/done {t1} '), ('Skip this step…', f'/cancel {t1}')]
    assert wf.settings(conn, P)['stage'] == 'plan_ready'
    approved = hc.handle(conn, 1, f'/plan {t1}', 'jd')
    assert approved.startswith(f'Plan approved for {t1}') and 'tests/test_hb_learning.py passes' in approved
    row = conn.execute('SELECT phase, state, plan_event_id FROM hb_task_manager WHERE task_id=?', (t1,)).fetchone()
    assert row[0] == 'execute' and row[1] == 'queued'
    plan_text = json.loads(conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?', (row[2],)).fetchone()[0])['next_action']
    assert plan_text.startswith('Owner-approved plan:\n1. Read export_dataset')
    from core.hb_dream_method import done_when
    assert done_when(conn, hb_tasks.get(conn, t1)) == ('owner', ['The dataset is re-exported after every verified task',
                                                                 'tests/test_hb_learning.py passes'])
    assert wf.settings(conn, P)['stage'] == 'running'
    hc.accept_step(conn, 'S-00000000A1', 'jd')                                          # owner approves the result
    wf.tick(conn)
    w = wf.settings(conn, P)
    assert w['task_id'] == t2 and w['stage'] == 'planning'                               # L2 waited for L1; it starts now
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '🔎 Next up:%' AND content LIKE '%step S-00000000A2%'").fetchone()[0] == 1


def test_owner_writes_own_done_or_skips_and_failures_ask_instead_of_guessing(plan):
    conn, principals, tasks = plan
    t1, t2 = tasks['S-00000000A1'], tasks['S-00000000A2']
    hc.handle(conn, 1, '/workflow on', 'jd')
    reply(conn, principals['apex'], _request(conn, t1), 'I looked around but I am not sure what to do.')
    wf.tick(conn)
    item = next(i for i in hc.waiting_items(conn, 1) if i['kind'] == 'plan')
    assert 'no "Done when" lines' in item['detail'] and item['actions'][0]['label'] == 'Ask APEX again'
    assert 'The workflow runs it now' in hc.handle(conn, 1, f'/done {t1} dataset re-exported after each accepted task', 'jd')
    assert conn.execute('SELECT phase, state FROM hb_task_manager WHERE task_id=?', (t1,)).fetchone() == ('execute', 'queued')
    hc.cancel_task(conn, t1, 'jd')                                                        # skipping L1 also skips its Studio step
    wf.tick(conn)
    assert wf.settings(conn, P)['task_id'] == t2


def test_owner_off_on_the_running_task_moves_the_workflow_on_and_stop_stops_it(plan):
    conn, _, tasks = plan
    t1, t5 = tasks['S-00000000A1'], tasks['S-00000000A5']
    hc.handle(conn, 1, '/workflow on', 'jd')
    hc.handle(conn, 1, f'/pause {t1}', 'jd')
    wf.tick(conn)
    assert wf.settings(conn, P)['task_id'] == t5                                          # L2 waits for L1, so A5 is next
    assert conn.execute("SELECT 1 FROM messages WHERE content LIKE '⏸ %is on hold%' AND content LIKE '%step S-00000000A1%'").fetchone()
    assert 'held by you' in next(s['skip'] for s in wf.steps(conn, P) if s['step_id'] == 'S-00000000A1')
    wf.stop_all(conn, 'jd via Stop')
    assert not wf.settings(conn, P)['enabled'] and continuation(conn, hb_tasks.get(conn, t5))['mode'] == 'off'


def test_next_lets_the_owner_choose_the_step(plan):
    conn, _, tasks = plan
    assert 'will be the next step' in hc.handle(conn, 1, '/workflow next S-00000000A5', 'jd')
    hc.handle(conn, 1, '/workflow on', 'jd')
    assert wf.settings(conn, P)['task_id'] == tasks['S-00000000A5']
    assert 'cannot start: waits for S-00000000A1' in hc.handle(conn, 1, '/workflow next S-00000000A2', 'jd')
    assert hc.parse('workflow next') is None and hc.parse('workflow start') == ('workflow', ['on'])


def test_parse_proposal_tolerates_markdown_and_one_line_lists():
    p = wf.parse_proposal('## Found: nothing yet\n**Done when:** export runs nightly; exam score is saved\nPlan:\n- step one\n- step two')
    assert p == {'found': ['nothing yet'], 'done_when': ['export runs nightly', 'exam score is saved'], 'plan': ['step one', 'step two']}
    assert wf.parse_proposal('no sections at all')['done_when'] == []


def test_closed_studio_step_closes_its_hb_task(plan):
    conn, _, tasks = plan
    conn.execute("UPDATE project_steps SET status='skipped' WHERE step_id='S-00000000A5'")
    conn.execute("UPDATE project_steps SET status='done' WHERE step_id='S-00000000A1'")
    assert sorted(hb_tasks.close_tasks_of_closed_steps(conn)) == sorted([tasks['S-00000000A5'], tasks['S-00000000A1']])
    assert hb_tasks.get(conn, tasks['S-00000000A5'])['state'] == 'cancelled'
    assert hb_tasks.get(conn, tasks['S-00000000A1'])['state'] == 'completed'
    assert hb_tasks.close_tasks_of_closed_steps(conn) == []


def test_work_turns_after_plan_approval_get_the_execution_tools_back(plan):
    """12 Nov live run: the read-only scoping limit leaked into L1's work turns, so APEX could only say
    "I will proceed" twice and HB stopped it. Work turns must get the normal execution tools."""
    conn, principals, tasks = plan
    t1 = tasks['S-00000000A1']
    hc.handle(conn, 1, '/workflow on', 'jd')
    reply(conn, principals['apex'], _request(conn, t1), PROPOSAL)
    wf.tick(conn)
    hc.handle(conn, 1, f'/plan {t1}', 'jd')
    tm.tick(conn)
    rid = _request(conn, t1)
    body = json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?', (rid,)).fetchone()[0])
    assert body['task_type'] == 'hb_managed_continuation'
    scope = json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE kind='tool_scope' AND request_id=?", (rid,)).fetchone()[0])
    assert 'propose_patch' in scope['allowed_tools'] and 'run_tests' in scope['allowed_tools']
    assert sorted(scope['allowed_tools']) == sorted(tm.EXECUTION_TOOLS)


def test_stop_all_is_a_stop():
    from core.hb_chat_controls import owner_text_stop
    assert owner_text_stop('stop all') and owner_text_stop('stop everything') and not owner_text_stop('stop the music')


def test_owner_keep_working_puts_a_stalled_task_back_to_work(plan):
    """13 Nov practice 1: Keep working on a task stopped at the review gate gave one turn, then the same question."""
    conn, _, tasks = plan
    t1 = tasks['S-00000000A1']
    task = hb_tasks.get(conn, t1)
    tm.register(conn, task)
    conn.execute("UPDATE hb_task_manager SET phase='review', recovery_count=3, state='needs_owner' WHERE task_id=?", (t1,))
    hc.handle(conn, 1, f'/continue {t1}', 'jd')
    assert conn.execute('SELECT phase, recovery_count FROM hb_task_manager WHERE task_id=?', (t1,)).fetchone() == ('execute', 0)


def test_step_dependencies_are_recorded_and_enforced():
    """Owner 13 Nov: when one task depends on another it must succeed before the next starts ('HB depends on: S-xxxx')."""
    import sqlite3
    from core import hb_plan_workflow as wf, hb_tasks, hb_task_manager
    conn = sqlite3.connect(':memory:'); conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, order_idx REAL)')
    hb_tasks.ensure_schema(conn)
    conn.execute("INSERT INTO project_steps VALUES('S-0000000001','P','Map','do it','todo','apex',1)")
    conn.execute("INSERT INTO project_steps VALUES('S-0000000002','P','Move','do it\nHB depends on: S-0000000001','todo','apex',2)")
    for n in (1, 2):
        conn.execute("INSERT INTO hb_tasks(task_id,conversation_id,root_message_id,title,objective,step_id,state,created_at,updated_at,version) "
                     "VALUES(?,1,?,?,?,?,'active',0,0,1)", (f'T-00000000000{n}', n, 't', 'o', f'S-000000000{n}'))
    assert wf.sync_step_dependencies(conn) == 1
    assert not hb_task_manager.dependencies_ready(conn, {'task_id': 'T-000000000002'})
    conn.execute("UPDATE hb_tasks SET state='completed' WHERE task_id='T-000000000001'")
    assert hb_task_manager.dependencies_ready(conn, {'task_id': 'T-000000000002'})
