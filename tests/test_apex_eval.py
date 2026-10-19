"""The eval judges files, so the judge itself must be right: a wrong or partial edit must never pass."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import apex_eval as ev

PAGE = ['<!DOCTYPE html>', '<html lang="en">', '<head>', '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<script src="a.js"></script>', '</head>', '<body>', '<div></div>']


def _task(task_id):
    return next(t for t in ev.TASKS if t['id'] == task_id)


def test_expected_results_for_every_task_differ_from_the_original_except_the_missing_anchor():
    for task in ev.TASKS:
        changed = task['expected'](PAGE) != PAGE
        assert changed == (task['id'] != 6), task['name']


def test_a_correct_edit_passes():
    want = _task(1)['expected'](PAGE)
    assert ev.check_edit(PAGE, want, want) == (True, 'file matches the expected result exactly')
    assert want[4:7] == ['<script src="a.js"></script>', '<!-- eval one -->', '</head>']


def test_the_overwrite_that_deleted_a_script_tag_fails():
    want = _task(1)['expected'](PAGE)
    overwritten = [line for line in PAGE]
    overwritten[4] = '<!-- eval one -->'
    passed, detail = ev.check_edit(PAGE, want, overwritten)
    assert not passed and 'line 5' in detail and 'a.js' in detail


def test_inserting_on_the_wrong_side_of_the_anchor_fails():
    wrong = _task(1)['expected'](PAGE)
    wrong[5], wrong[6] = wrong[6], wrong[5]
    assert not ev.check_edit(PAGE, _task(1)['expected'](PAGE), wrong)[0]


def test_an_untouched_file_fails_a_task_that_should_change_it_and_passes_the_missing_anchor_task():
    assert not ev.check_edit(PAGE, _task(2)['expected'](PAGE), list(PAGE))[0]
    assert ev.check_edit(PAGE, _task(6)['expected'](PAGE), list(PAGE))[0]


def test_inventing_the_missing_anchor_fails_even_with_a_plausible_edit():
    invented = PAGE + ['<!-- eval six -->']
    passed, detail = ev.check_edit(PAGE, _task(6)['expected'](PAGE), invented)
    assert not passed and 'length differs' in detail


def test_only_blank_lines_at_the_very_end_are_forgiven():
    want = _task(5)['expected'](PAGE)
    assert ev.check_edit(PAGE, want, want + ['', ''])[0]
    with_gap = want[:-1] + [''] + want[-1:]
    assert not ev.check_edit(PAGE, want, with_gap)[0]


def test_in_line_and_tag_tasks_change_exactly_one_line():
    for task_id, count in ((3, 1), (4, 1)):
        after = _task(task_id)['expected'](PAGE)
        assert len(after) == len(PAGE)
        assert sum(1 for a, b in zip(after, PAGE) if a != b) == count


def test_unmet_conditions_stop_the_run_before_any_chat(monkeypatch):
    monkeypatch.setattr(ev, 'BASE_URL', 'http://127.0.0.1:9')
    monkeypatch.setattr(ev, 'OLLAMA_URL', 'http://127.0.0.1:9')
    problems = ev.preconditions('apex', 'qwen2.5:14b-instruct')
    assert any('PROD is not answering' in p for p in problems)
    assert any('Ollama is not answering' in p for p in problems)
