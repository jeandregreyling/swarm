"""Practice 195: a focused test run (-k) never counts as the step's check."""
from core import apex_alm


def _setup(monkeypatch):
    starts = []
    from core.knowledge import test_runs
    monkeypatch.setattr(apex_alm, '_apex_case', lambda case_id: {'case_id': 'C-1', 'project_id': 'P', 'step_id': 'S-1', 'title': 'Guarded checks'})
    monkeypatch.setattr(test_runs, 'start_run', lambda *a, **kw: starts.append(kw.get('case_id')) or 'R-1')
    monkeypatch.setattr(test_runs, 'finish_run', lambda *a, **kw: True)
    return starts


def test_focused_run_is_not_the_steps_check(monkeypatch):
    starts = _setup(monkeypatch)
    out = apex_alm.run_recorded_tests({'tests': ['tests/test_x.py'], 'keyword': 'test_one'},
                                      lambda a: {'status': 'passed', 'verdict': 'PASS: 1 passed, 33 deselected', 'exit_code': 0},
                                      validate=lambda a: a)
    assert starts == [None] and out['alm_run_status'] == 'focused' and "does not count as the step's check" in out['note']


def test_whole_check_still_rolls_up(monkeypatch):
    starts = _setup(monkeypatch)
    out = apex_alm.run_recorded_tests({'tests': ['tests/test_x.py']},
                                      lambda a: {'status': 'passed', 'verdict': 'PASS: 34 passed', 'exit_code': 0}, validate=lambda a: a)
    assert starts == ['C-1'] and out['alm_run_status'] == 'pass'


def test_ready_ignores_deselected_passes():
    src = open('core/hb_task_manager.py').read()
    assert "NOT LIKE '%deselected%'" in src
