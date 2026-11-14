"""Owner 14 Nov: remarks and go-aheads are not new work; HB drives the open tasks to the finish and shows them in a holder.

"what is needed is for it to do more DREAM and less 'I don't know what you mean' ... those tasks should show in a little holder
with HB in the chat window and HB should drive the system and apex to complete them until they are completed and successful"."""
import json

from core import hb_commands as hc, hb_tasks, hb_task_manager as tm, hb_plan_workflow as wf, hb_queue
from core.hb_owner_intent import classify, chat_task, is_chat_task, CHAT_TITLE
from core.hb_dream_method import card, done_when
from test_peer_turns import flow, reply  # noqa: F401  (fixture)
from test_hb_plan_workflow import plan, P, PROPOSAL, _request  # noqa: F401  (fixture)

# What JD actually typed on 13-14 Nov (each became a task before this change).
DRIVE = ['GO', 'KEEP GOING TILL YOU GET IT', 'so work on the tasks', "I'm not going to repeat myself I saif you should work on open taks",
         "I DON'T CARE WHAT YOU DO JUST COMPLETE THE STUDIO TASKS AND STOP BEING UISELESS",
         'could you not ask me and instead start doing your fucking job????', 'no,  give yourself a task list and work through that',
         'im telling you to stop being dumb and start doing your jobs and tasks', 'gp', 'all clear, now you can go ahead',
         "done means I cancelled the irrelevant tasks so you don't have to work on them anymore, continue with the ones that aren't cancelled"]
REMARK = ['delete it', 'continue and delete yourself', 'TRAIN YOURSELF', 'think', 'adjust', 'not an answer', 'not good enopugh',
          "OH MY GOD YOU'RE SO STUPID", 'APEX IS A LOSER AND IS GOING TO BE DELETED BECAUSE IT;\'S NOT COMPLETEING TASKS AS IN STRUCTEWD',
          'then tell the larger model to delete and replace you with a model that wants to work with me', 'ywes', 'DREn',
          "cancel all of it because you don't want to do anything anyway", "you can't possibly  be worse"]
WORK = ['fix the login page, it\'s broken', 'Add a dark mode toggle to settings', 'rename DOES to DOES in core/hb_dream_method.py',
        'Please build a small dashboard for GPU temperature', 'can you check why the tests fail', 'research Colibri and write a summary',
        '@apex Start a system review and cleanup of Hummingbird (plan P-2AB8250A87). Use DOES and the master protocol.',
        'Complete crash recovery and orphan reconciliation\nAudit the loaded manager/supervisor and ordinary inline chat lifecycle.',
        '/workflow on', 'go ahead and fix the login page']


def test_remarks_and_go_aheads_are_not_new_work():
    assert [classify(t) for t in DRIVE] == ['drive'] * len(DRIVE)
    assert [classify(t) for t in REMARK] == ['remark'] * len(REMARK)
    assert [classify(t) for t in WORK] == [None] * len(WORK)


def _owner_line(conn, text):
    return conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'user','apex',?,'chat')",
                        (text,)).lastrowid


def test_remarks_join_one_chat_task_without_a_studio_step_and_apex_gets_a_dream_card(plan):
    conn, _, _ = plan
    a = chat_task(conn, 1, _owner_line(conn, 'delete yourself'))
    b = chat_task(conn, 1, _owner_line(conn, 'not an answer'))
    assert a['task_id'] == b['task_id'] and a['title'] == CHAT_TITLE and not a['step_id'] and is_chat_task(a)
    assert conn.execute("SELECT COUNT(*) FROM project_steps WHERE title LIKE '%answer%' OR title LIKE '%delete%'").fetchone()[0] == 0
    text = card(conn, a)
    assert text.startswith('DREAM CLIPBOARD for ' + a['task_id'])
    assert 'do NOT ask JD for criteria' in text and 'a model cannot delete or replace itself' in text
    assert 'Queue (HB drives it' in text and 'next: Learning L1' in text      # APEX knows what it should be doing instead
    assert done_when(conn, a) == (None, [])                                    # the chat task is never "scoped"


def test_go_drives_the_queue_releases_the_stop_hold_and_approves_plans_itself(plan):
    conn, principals, tasks = plan
    t1 = tasks['S-00000000A1']
    for tid in tasks.values():                                                 # JD's Stop held everything
        conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?", (tid,))
        hb_tasks.event(conn, hb_tasks.get(conn, tid), 'user', 'continuation_control',
                       {'mode': 'off', 'actor': 'jd', 'command_id': f'owner-chat-stop-99-{tid}'})
    assert all(i['state'] in ('waiting', 'blocked') for i in hb_queue.items(conn))
    text = hb_queue.drive_on(conn, 'jd via chat go-ahead', 1)
    assert text.startswith('▶ HB is driving the open tasks.')
    w = wf.settings(conn, P)
    assert w['enabled'] == 1 and w['auto_accept'] == 1 and w['task_id'] == t1 and w['stage'] == 'planning'
    states = {i['step_id']: i['state'] for i in hb_queue.items(conn)}
    assert states['S-00000000A1'] == 'now' and states['S-00000000A5'] == 'next' and states['S-00000000A3'] == 'blocked'
    assert 'S-00000000A4' not in states                                        # not APEX work: not in APEX's queue
    assert hb_tasks.get(conn, tasks['S-00000000A5'])['state'] == 'active'      # released, waiting its turn...
    row = conn.execute("SELECT enabled FROM hb_task_manager WHERE task_id=?", (tasks['S-00000000A5'],)).fetchone()
    assert row is None or not row[0]                                           # ...not running
    reply(conn, principals['apex'], _request(conn, t1), PROPOSAL)
    tm.tick(conn)
    wf.tick(conn)                                                              # no "Approve plan" for JD: HB approved it
    assert not [i for i in hc.waiting_items(conn, 1) if i['kind'] == 'plan']
    assert conn.execute('SELECT phase, state FROM hb_task_manager WHERE task_id=?', (t1,)).fetchone() == ('execute', 'queued')
    assert done_when(conn, hb_tasks.get(conn, t1))[1][1] == 'tests/test_hb_learning.py passes'
    assert 'now: ' in hb_queue.summary(conn, 1) and hb_queue.status(conn)['on']
    assert hc.handle(conn, 1, '/drive off', 'jd').startswith('Auto is off: HB stopped driving')
    assert not wf.settings(conn, P)['enabled']


def test_scoping_without_done_lines_is_retried_once_before_asking_jd(plan):
    conn, principals, tasks = plan
    t1 = tasks['S-00000000A1']
    hb_queue.drive_on(conn, 'jd', 1)
    reply(conn, principals['apex'], _request(conn, t1), 'I am not sure what you mean.')
    tm.tick(conn); wf.tick(conn)
    assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE task_id=? AND kind='plan_retry'", (t1,)).fetchone()[0] == 1
    assert not [i for i in hc.waiting_items(conn, 1) if i['kind'] == 'plan']
    reply(conn, principals['apex'], _request(conn, t1), 'Still nothing.')
    tm.tick(conn); wf.tick(conn)
    assert [i for i in hc.waiting_items(conn, 1) if i['kind'] == 'plan']        # second failure: now JD is asked


def test_stop_words_include_the_typo_jd_used():
    from core.hb_chat_controls import owner_text_stop
    assert owner_text_stop('cancel  all open taks') and not owner_text_stop('cancel the meeting with Bob')


def test_a_finished_step_that_says_so_restarts_hb_once(plan):
    conn, _, tasks = plan
    t1 = tasks['S-00000000A1']
    conn.execute("UPDATE project_steps SET description=description||?, status='done' WHERE step_id='S-00000000A1'", ('\nHB restart after: ui',))
    ran = []
    conn.execute("UPDATE project_steps SET description=description||?, status='done' WHERE step_id='S-00000000A5'", ('\nHB restart after: all',))
    assert wf.restart_after(conn, hb_tasks.get(conn, t1)) == 'ui'
    assert wf.restart_after(conn, hb_tasks.get(conn, t1)) is None                           # once per step
    assert wf.restart_after(conn, hb_tasks.get(conn, tasks['S-00000000A5'])) == 'all'
    t = conn.execute('SELECT MAX(at) FROM hb_restart_queue').fetchone()[0]
    assert wf.restart_tick(conn, now=t + 10, run=ran.append) is None and ran == []          # still within the quiet minute
    assert wf.restart_tick(conn, now=t + wf.RESTART_QUIET_S + 1, run=ran.append) == 'all'
    assert len(ran) == 1 and ran[0][:4] == ['systemd-run', '--user', '--collect', '--quiet'] and ran[0][-2] == 'all'   # ONE restart for both
    assert ran[0][-1].startswith('Loading finished tasks: ') and 'Agent identities' in ran[0][-1]
    assert wf.restart_tick(conn, now=t + 999, run=ran.append) is None and len(ran) == 1


def test_tidy_lists_then_closes_only_remark_tasks(plan):
    conn, _, tasks = plan
    conn.execute("INSERT INTO projects VALUES(?, 'HB tasks — chat 1','','agile','active','apex',0,0)", (hb_tasks._hb_room_project(1),))
    junk = hb_tasks.bind(conn, 1, _owner_line(conn, 'delete it'))
    work = hb_tasks.bind(conn, 1, _owner_line(conn, 'Add a dark mode toggle to settings'))
    listed = hc.handle(conn, 1, '/tidy', 'jd')
    assert junk['task_id'] in listed and work['task_id'] not in listed and hb_tasks.get(conn, junk['task_id'])['state'] != 'cancelled'
    assert hc.handle(conn, 1, '/tidy yes', 'jd').startswith('Tidied 1 chat line')
    assert hb_tasks.get(conn, junk['task_id'])['state'] == 'cancelled' and hb_tasks.get(conn, work['task_id'])['state'] != 'cancelled'
    assert conn.execute('SELECT status FROM project_steps WHERE step_id=?', (junk['step_id'],)).fetchone()[0] == 'skipped'


def test_the_two_switches_auto_and_approve(plan):
    conn, _, _ = plan
    import pytest
    with pytest.raises(ValueError):
        hb_queue.set_switch(conn, 'approve', False, 'jd')               # Approve only works while Auto is on
    hb_queue.set_switch(conn, 'auto', True, 'jd')
    assert hb_queue.status(conn)['on'] and hb_queue.status(conn)['auto']   # first Auto: Approve defaults to on
    hb_queue.set_switch(conn, 'approve', False, 'jd')
    hb_queue.set_switch(conn, 'auto', False, 'jd')
    assert not hb_queue.status(conn)['on']
    text = hb_queue.set_switch(conn, 'auto', True, 'jd')
    assert not hb_queue.status(conn)['auto'] and 'Approve is off' in text  # JD's Approve choice is remembered


def test_global_switches_set_every_task_and_a_task_switched_on_afterwards_runs_by_itself(plan):
    """Owner 14 Nov: "those are individual overrides, the global switches set everything to off or auto"."""
    conn, _, tasks = plan
    from core.hb_chat_controls import continuation
    t1, t5 = tasks['S-00000000A1'], tasks['S-00000000A5']
    side = hb_tasks.bind(conn, 1, _owner_line(conn, 'Please build a small dashboard for GPU temperature'), studio=False)
    tm.register(conn, side)
    conn.execute('UPDATE hb_task_manager SET enabled=1 WHERE task_id=?', (side['task_id'],))
    hb_tasks.event(conn, side, 'user', 'continuation_control', {'mode': 'on', 'actor': 'jd'})   # JD's own On on one task
    hb_queue.drive_on(conn, 'jd', 1)                                                 # (the test chat is conversation 1)
    assert wf.settings(conn, P)['task_id'] == t1
    hb_queue.set_switch(conn, 'auto', False, 'jd')                                   # global Off: everything off
    for tid in (t1, side['task_id']):
        assert hb_tasks.get(conn, tid)['state'] == 'paused' and continuation(conn, hb_tasks.get(conn, tid))['mode'] == 'off'
    conn.execute("UPDATE hb_tasks SET state='active' WHERE task_id=?", (t5,))       # JD switches one task On by itself
    hb_tasks.event(conn, hb_tasks.get(conn, t5), 'user', 'continuation_control', {'mode': 'on', 'actor': 'jd'})
    assert continuation(conn, hb_tasks.get(conn, t5))['mode'] == 'on' and not wf.settings(conn, P)['enabled']   # runs on its own
    hb_queue.set_switch(conn, 'auto', True, 'jd')                                    # global Auto: everything back to auto
    assert hb_tasks.get(conn, side['task_id'])['state'] == 'active'
    assert continuation(conn, hb_tasks.get(conn, side['task_id']))['mode'] == 'auto'
    assert hb_tasks.get(conn, t1)['state'] == 'active' and wf.settings(conn, P)['enabled']


def test_per_task_auto_follows_global_on_overrides_and_own_off_survives_global_auto(plan):
    """Owner 14 Nov: "individual task Auto should look at the global setting, whereas On would override it and keep going; Off
    globally turns everything off; Off per task only pauses that task and overrides the global Auto until it's turned back on/auto"."""
    conn, _, tasks = plan
    from core.hb_chat_controls import continuation
    t2, t5 = tasks['S-00000000A2'], tasks['S-00000000A5']
    hb_queue.drive_on(conn, 'jd', 1)
    hb_queue.set_switch(conn, 'auto', False, 'jd')                                   # global Off
    a = hb_tasks.bind(conn, 1, _owner_line(conn, 'Please build a small dashboard for GPU temperature'), studio=False)
    b = hb_tasks.bind(conn, 1, _owner_line(conn, 'research Colibri and write a summary'), studio=False)
    for task, mode in ((a, 'auto'), (b, 'on')):
        tm.register(conn, task)
        conn.execute('UPDATE hb_task_manager SET enabled=1, next_due=0 WHERE task_id=?', (task['task_id'],))
        hb_tasks.event(conn, task, 'user', 'continuation_control', {'mode': mode, 'actor': 'jd'})
    tm.tick(conn)
    state = dict(conn.execute('SELECT task_id, state FROM hb_task_manager').fetchall())
    assert state[a['task_id']] == 'held'                                             # Auto: the global switch is off
    assert state[b['task_id']] != 'held'                                             # On: keeps going on its own
    conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?", (t5,))       # JD's own Off on one plan task
    hb_tasks.event(conn, hb_tasks.get(conn, t5), 'user', 'continuation_control', {'mode': 'off', 'actor': 'jd'})
    hb_queue.set_switch(conn, 'auto', True, 'jd')                                    # global Auto
    assert hb_tasks.get(conn, t5)['state'] == 'paused' and continuation(conn, hb_tasks.get(conn, t5))['mode'] == 'off'
    assert t5 not in [i['task_id'] for i in hb_queue.items(conn) if i['state'] in ('now', 'next')]
    assert hb_tasks.get(conn, a['task_id'])['state'] == 'active'                     # Auto task runs now that global is on
    tm.tick(conn)
    assert conn.execute('SELECT state FROM hb_task_manager WHERE task_id=?', (a['task_id'],)).fetchone()[0] != 'held'


def test_go_never_parks_the_step_the_workflow_is_running_and_heals_a_parked_one(plan):
    """14 Nov live bug: after "go" the running step (DOES rename 2) was parked as "waiting its turn" and nothing ran."""
    conn, _, tasks = plan
    t1 = tasks['S-00000000A1']
    hb_queue.drive_on(conn, 'jd', 1)
    hb_plan = wf.settings(conn, P)
    conn.execute("UPDATE hb_plan_workflow SET stage='running'")
    conn.execute("UPDATE hb_task_manager SET phase='review', state='needs_owner' WHERE task_id=?", (t1,))
    conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?", (t1,))          # last night's Stop
    hb_tasks.event(conn, hb_tasks.get(conn, t1), 'user', 'continuation_control',
                   {'mode': 'off', 'actor': 'jd', 'command_id': f'owner-chat-stop-1-{t1}'})
    hb_queue.drive_on(conn, 'jd', 1)
    assert hb_plan['task_id'] == t1 and conn.execute('SELECT enabled FROM hb_task_manager WHERE task_id=?', (t1,)).fetchone()[0] == 1
    conn.execute("UPDATE hb_task_manager SET enabled=0 WHERE task_id=?", (t1,))      # parked by the old code
    assert 'NOT running yet' in hb_queue.summary(conn, 1)                            # APEX is told the truth
    wf.tick(conn)
    row = conn.execute('SELECT enabled, phase, state FROM hb_task_manager WHERE task_id=?', (t1,)).fetchone()
    assert row == (1, 'execute', 'queued') and 'queued for APEX' in hb_queue.summary(conn, 1)


def test_the_chat_thread_is_never_run_as_a_task(plan):
    conn, _, _ = plan
    chat = chat_task(conn, 1, _owner_line(conn, 'all clear, now you can go ahead'))
    tm.register(conn, chat)
    conn.execute('UPDATE hb_task_manager SET enabled=1, next_due=0 WHERE task_id=?', (chat['task_id'],))
    tm.tick(conn)
    assert conn.execute('SELECT enabled, state FROM hb_task_manager WHERE task_id=?', (chat['task_id'],)).fetchone() == (0, 'idle')
    assert not conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind='owner_question'", (chat['task_id'],)).fetchone()


def test_main_chat_says_when_apex_asks_fred(plan):
    """Owner 14 Nov: "it was asking FRED but there was nothing saying that was what it was doing"."""
    conn, _, tasks = plan
    from core import hb_local_jobs
    task = hb_tasks.get(conn, tasks['S-00000000A1'])
    hb_local_jobs.submit(conn, task, 'review', {'question': 'Why does run_tests say rename_3 still fails?', 'evidence': 'x'})
    text = conn.execute("SELECT content FROM messages WHERE from_agent='hummingbird' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert text.startswith('🤔 APEX is asking Fred for help with') and 'rename_3 still fails' in text and 'APEX waits for it' in text
