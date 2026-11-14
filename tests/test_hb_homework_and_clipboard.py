"""Owner 14 Nov: homework on the CPU (small models scope and spec a task before the GPU model runs it) and HB's clipboard
(one editable list; importance, doer and pins reshuffle it; finished tasks drop off)."""
import json

from core import hb_tasks, hb_task_manager as tm, hb_plan_workflow as wf, hb_queue, hb_homework, hb_clipboard, hb_commands as hc
from core.hb_dream_method import card as dream_card, done_when
from test_peer_turns import flow, reply  # noqa: F401
from test_hb_plan_workflow import plan, P  # noqa: F401

GOOD = {'goal': 'Make waiting approvals visible in the header', 'check': 'tests/test_hb_approval_popup.py passes',
        'plan': ['Read hb-needs-you.js dial()', 'Add the glow'], 'files': ['frontend/static/js/views/hb-needs-you.js', 'made/up.py'],
        'questions': [], 'doer': 'apex', 'importance': 4, 'why': 'code change in the page'}


def test_facts_come_from_hb_tools_not_the_model(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A5'])
    conn.execute('UPDATE hb_tasks SET objective=? WHERE task_id=?',
                 ('Make the approvals glow: see frontend/static/js/views/hb-needs-you.js function hbNeedsFocusBar', task['task_id']))
    gathered = hb_homework.facts(conn, hb_tasks.get(conn, task['task_id']))
    paths = [f['path'] for f in gathered['files']]
    assert 'frontend/static/js/views/hb-needs-you.js' in paths
    assert any('hbNeedsFocusBar' in l['text'] for f in gathered['files'] for l in f['lines'])


def test_hb_judges_the_card_and_drops_invented_files(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A5'])
    gathered = {'files': [{'path': 'frontend/static/js/views/hb-needs-you.js', 'lines': []}], 'done_when': [], 'done_source': None}
    ok, why = hb_homework.judge(dict(GOOD), gathered)
    assert ok and not why
    vague = {**GOOD, 'check': 'Verify that it works'}
    assert not hb_homework.judge(vague, gathered)[0]
    asks = {**GOOD, 'questions': ['Which colour?']}
    assert 'open question for JD' in hb_homework.judge(asks, gathered)[1][0]
    card = hb_homework.write(conn, task, model=lambda messages: dict(GOOD))
    assert card['files'] == [] or 'made/up.py' not in card['files']           # never a path HB did not find
    assert hb_homework.latest(conn, task)['goal'] == GOOD['goal']


def test_a_ready_card_replaces_the_gpu_scoping_turn_and_apex_sees_it(plan):
    conn, _, tasks = plan
    t1 = tasks['S-00000000A1']
    task = hb_tasks.get(conn, t1)
    conn.execute('UPDATE hb_tasks SET objective=? WHERE task_id=?', ('Harvest examples: see frontend/static/js/views/hb-needs-you.js', t1))
    task = hb_tasks.get(conn, t1)
    hb_homework.write(conn, task, model=lambda messages: {**GOOD, 'files': ['frontend/static/js/views/hb-needs-you.js']})
    assert hb_homework.latest(conn, task)['ready']
    hb_queue.drive_on(conn, 'jd', 1)
    w = wf.settings(conn, P)
    assert w['task_id'] == t1 and w['stage'] == 'running'                     # no 'planning' turn on the GPU
    assert done_when(conn, task)[1] == ['tests/test_hb_approval_popup.py passes']
    text = dream_card(conn, task)
    assert 'Homework (spec card by homework-cpu:7b on the CPU; READY)' in text and 'check: tests/test_hb_approval_popup.py passes' in text


def test_homework_failure_falls_back_to_the_old_scoping(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A1'])
    def broken(messages):
        raise RuntimeError('model not loaded')
    card = hb_homework.write(conn, task, model=broken)
    assert not card['ready'] and 'homework model failed' in card['why']
    hb_queue.drive_on(conn, 'jd', 1)
    assert wf.settings(conn, P)['stage'] == 'planning'


def test_candidates_are_the_coming_steps_without_done_criteria(plan):
    conn, _, tasks = plan
    hb_queue.drive_on(conn, 'jd', 1)                                          # A1 is running
    ids = [t['task_id'] for t in hb_homework.candidates(conn)]
    assert tasks['S-00000000A1'] not in ids and tasks['S-00000000A5'] in ids


def test_clipboard_importance_pins_and_doer_reorder_the_queue(plan):
    conn, _, tasks = plan
    steps = [s for s in wf.steps(conn, P) if not s['skip']]
    assert [s['step_id'] for s in hb_clipboard.ordered(conn, steps)] == ['S-00000000A1', 'S-00000000A5']
    assert hc.handle(conn, 1, '/clip importance S-00000000A5 5', 'jd').startswith('Clipboard: S-00000000A5 importance 5 (jd)')
    assert wf.next_ready(conn, P)['step_id'] == 'S-00000000A5'                 # importance decides what starts next
    hc.handle(conn, 1, '/clip top S-00000000A1', 'apex')
    assert wf.next_ready(conn, P)['step_id'] == 'S-00000000A1'                 # a pin beats importance
    hc.handle(conn, 1, '/clip doer S-00000000A5 small', 'claude-code')
    row = next(r for r in hb_clipboard.rows(conn) if r['step_id'] == 'S-00000000A5')
    assert row['doer'] == 'small' and row['importance'] == 5 and 'set by claude-code' in row['why']
    hc.handle(conn, 1, '/clip clear S-00000000A5', 'jd')
    assert next(r for r in hb_clipboard.rows(conn) if r['step_id'] == 'S-00000000A5')['doer'] == 'apex'
    edits = conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='clipboard_edit'").fetchone()[0]
    assert edits == 4


def test_the_holder_data_carries_the_clipboard_columns(plan):
    conn, _, tasks = plan
    rows = hb_queue.status(conn, 1)['items']
    assert {'doer', 'importance', 'ready', 'check_result'} <= set(rows[0])
    assert rows[-1]['state'] == 'blocked'


def test_studio_steps_reach_the_knowledge_centre(plan):
    """Owner 14 Nov: the FILE LOG and every Studio step must be in the KC, not only in Studio."""
    conn, _, _ = plan
    conn.executescript('''CREATE TABLE IF NOT EXISTS knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, source_type TEXT, source_ref TEXT,
        raw_text TEXT, domain_tags TEXT, added_by TEXT, category TEXT, subcategory TEXT, content_hash TEXT, chunk_count INT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS knowledge_chunks(source_id INT, chunk_index INT, chunk_text TEXT, embedding BLOB);''')
    from core import hb_kc_records as kc
    written = kc.index_steps(conn)
    assert 'S-00000000A5' in written
    text = conn.execute("SELECT raw_text FROM knowledge_sources WHERE source_ref='studio://step/S-00000000A5'").fetchone()[0]
    assert 'Agent identities' in text and 'Status: todo' in text
    assert kc.index_steps(conn) == []                                          # unchanged steps are not rewritten
    conn.execute("UPDATE project_steps SET description='FILE LOG: changed core/x.py', updated_at=updated_at+100 WHERE step_id='S-00000000A5'")
    assert kc.index_steps(conn) == ['S-00000000A5']
    assert 'FILE LOG: changed core/x.py' in conn.execute("SELECT raw_text FROM knowledge_sources WHERE source_ref='studio://step/S-00000000A5'").fetchone()[0]


def test_a_stuck_step_is_parked_and_the_queue_moves_on(plan):
    """Owner 14 Nov: "all tasks are stalled again" - one stuck step (a vague one) held the whole list."""
    conn, _, tasks = plan
    t1, t5 = tasks['S-00000000A1'], tasks['S-00000000A5']
    conn.execute("UPDATE hb_tasks SET objective=objective||? WHERE task_id IN (?,?)", ('\nDone when: tests pass', t1, t5))
    hb_queue.drive_on(conn, 'jd', 1)
    assert wf.settings(conn, P)['task_id'] == t1
    conn.execute("UPDATE hb_task_manager SET state='needs_owner', detail='Stopped, not looping: grep_repo failed 3 times' WHERE task_id=?", (t1,))
    wf.tick(conn)
    assert wf.settings(conn, P)['task_id'] == t5                               # moved on
    assert hb_tasks.get(conn, t1)['state'] == 'paused'
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '⏸ Parked%'").fetchone()[0] == 1
    hb_queue.drive_on(conn, 'jd', 1)                                           # a go-ahead does not wake a parked step...
    assert hb_tasks.get(conn, t1)['state'] == 'paused'
    hc.handle(conn, 1, f'/continue {t1}', 'jd')                                # ...only JD's /continue does
    assert hb_tasks.get(conn, t1)['state'] == 'active'


def test_a_step_whose_homework_is_not_ready_waits_for_a_spec(plan):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks['S-00000000A1'])
    hb_homework.write(conn, task, model=lambda m: {**GOOD, 'check': 'Verify that it works'})
    skip = next(s['skip'] for s in wf.steps(conn, P) if s['step_id'] == 'S-00000000A1')
    assert skip.startswith('needs a spec: the check is not concrete')
    hb_queue.drive_on(conn, 'jd', 1)
    assert wf.settings(conn, P)['task_id'] == tasks['S-00000000A5']           # the vague step is not started
