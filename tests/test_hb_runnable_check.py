"""Practice 36 (owner 14 Nov): HB does not start a step for APEX unless its Done-when has a runnable check - Potato Farm, the DAW review,
live acceptance, main chat and cleanup 2 each went round 8 rounds because their Done-when was prose."""
from pathlib import Path
from core import hb_plan_workflow as wf


def test_practice_36_runnable_checks_are_recognised():
    assert wf.runnable_check('python -m pytest tests/test_hb_agents.py passes')
    assert wf.runnable_check('run_tests with tests/test_x.py')
    assert not wf.runnable_check('Create a detailed spec and scope the review items works')
    assert wf.runnable_check('tests pass') and not wf.runnable_check('')


def test_practice_36_needs_spec_uses_it():
    src = Path(wf.__file__).read_text()
    i = src.index('def _needs_spec')
    assert 'runnable_check(crit)' in src[i:i + 1600]
