"""Practice 27 (owner 14 Nov): HB looks into the vague steps itself - what exists, why it is not working, options - and JD picks."""
import json

from core import hb_tasks, hb_commands as hc, hb_plan_workflow as wf
from test_peer_turns import flow, reply  # noqa: F401
from test_hb_plan_workflow import plan, P  # noqa: F401

CARD = {'exists': ['core/hb_activity.py shows live work'], 'why_not_working': 'Nobody defined what a "visual review" checks.',
        'options': [{'title': 'Checklist review', 'how': 'Write a 10-point visual checklist and a test for each point', 'effort': 'M', 'risk': 'slow'},
                    {'title': 'Screenshot diff', 'how': 'Compare screenshots before and after', 'effort': 'L', 'risk': 'flaky'}],
        'recommended': 1, 'first_step': 'Write the checklist as tests/test_visual_checklist.py', 'check': 'tests/test_visual_checklist.py passes'}


def test_practice_27_counsel_reviews_a_vague_step_and_jd_picks():
    import pytest
    pytest.importorskip('core.hb_counsel')


def test_practice_27_vague_steps_get_options_and_a_pick_becomes_the_spec(plan):
    from core import hb_counsel
    conn, _, tasks = plan
    conn.execute("UPDATE project_steps SET description=description||? WHERE step_id='S-00000000A5'", ('\n' + wf.SPEC_MARK + ' counsel first',))
    todo = hb_counsel.candidates(conn)
    assert 'S-00000000A5' in [s['step_id'] for s, _ in todo]
    why = dict((s['step_id'], w) for s, w in todo)['S-00000000A5']
    task = hb_tasks.get(conn, tasks['S-00000000A5'])
    seen = []
    card = hb_counsel.review(conn, task, why, model=lambda messages: seen.append(messages) or dict(CARD))
    assert 'Never invent files' in seen[0][0]['content'] and card['recommended'] == 1
    text = conn.execute("SELECT content FROM messages WHERE from_agent='hummingbird' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert text.startswith('🔎 HB looked into') and '1. Checklist review (M)' in text and '/pick S-00000000A5 N' in text
    assert 'S-00000000A5' not in [s['step_id'] for s, _ in hb_counsel.candidates(conn)]   # not looked at again for a week
    answer = hc.handle(conn, 1, '/pick S-00000000A5 1', 'jd')
    assert answer.startswith('S-00000000A5: option 1 (Checklist review) is now its spec')
    desc = conn.execute("SELECT description FROM project_steps WHERE step_id='S-00000000A5'").fetchone()[0]
    assert 'Done when: tests/test_visual_checklist.py passes' in desc
    from core.hb_dream_method import done_when
    assert 'tests/test_visual_checklist.py passes' in done_when(conn, hb_tasks.get(conn, tasks['S-00000000A5']))[1][0]


def test_practice_28_counsel_finds_existing_studio_work_and_waits_for_the_queue(plan):
    """Owner 14 Nov: "there's already a lot of work done behind all of them - it's just not been scoped or recorded in Studio"; and "let the
    current tasks finish, then use the homework models to propose the spec"."""
    from core import hb_counsel, hb_queue
    conn, _, tasks = plan
    conn.execute("INSERT INTO projects VALUES('P-OLD0000001','Media Center + Studio Integration','','agile','archived','jd',0,0)")
    conn.execute("INSERT INTO project_steps VALUES('S-OLD0000001','P-OLD0000001','Agent identities review done',"
                 "'Identities and logins for every agent were built in core/agent_identity.py','done','apex',1,0,0,NULL)")
    task = hb_tasks.get(conn, tasks['S-00000000A5'])                          # "Agent identities"
    facts = hb_counsel.gather(conn, task)
    assert any(s['step_id'] == 'S-OLD0000001' and s['status'] == 'done' for s in facts['studio'])
    seen = []
    hb_counsel.review(conn, task, 'not scoped in Studio yet', model=lambda m: seen.append(m) or dict(CARD))
    assert 'not new' in seen[0][0]['content'] and 'what is left' in seen[0][0]['content']
    hb_queue.drive_on(conn, 'jd', 1)                                          # the queue has precise work running
    assert not hb_counsel.can_run(conn)
    hb_queue.drive_off(conn, 'jd', 1)
    assert hb_counsel.can_run(conn)
