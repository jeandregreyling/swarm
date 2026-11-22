"""Practice 289 (JD 22 Nov: "we now have 15 open tasks, doesn't look like APEX is having any success"): in two hours APEX saved 16 task plans
and tried one patch, because task_plan counted as an action. On HB's own work turns a new plan, a memory note or a status read is not work."""
from core.apex_tools import NO_WORK_NOTICE, no_work

CONT = '{"task_type": "hb_managed_continuation", "task_id": "T-1", "instruction": "Continue"}'
PLAN = {'tool': 'task_plan', 'status': 'succeeded'}
READ = {'tool': 'read_file', 'status': 'succeeded'}


def test_reading_and_replanning_is_not_work():
    assert no_work('Next I will patch core/x.py.', [READ, PLAN, PLAN], CONT)
    assert no_work('Saved.', [{'tool': 'memory_save', 'status': 'succeeded'}], CONT)
    assert 'a new task_plan is not progress' in NO_WORK_NOTICE


def test_a_patch_a_write_or_a_test_run_is_work():
    for tool in ('propose_patch', 'propose_write_file', 'run_tests', 'change_set'):
        assert not no_work('Done.', [READ, PLAN, {'tool': tool, 'status': 'succeeded'}], CONT), tool
