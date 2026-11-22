"""Practice 295: the BA still invented core/hb_phone_flow.py because tests reach the code through imports ('from core import hb_channels'),
not paths - those modules are now in its facts; and a step that names the file and the function is concrete even if it says 'ensure'."""
from core import hb_homework as hw


def test_imported_modules_of_the_test_are_facts():
    files = hw.test_files('Done when: tests/test_hb_phone_owner_execution.py passes')
    assert any(p.startswith('core/') and p.endswith('.py') for p in files if not p.startswith('tests/')), files


def test_a_step_with_file_and_function_is_not_vague():
    known = {'core/hb_channels.py'}
    ok = hw.plan_problems(['In core/hb_channels.py fix _reply_target to ensure each reply keeps its question'], known, {'done_when': []})
    assert not any('vague' in p for p in ok)
    assert any('vague' in p for p in hw.plan_problems(['Ensure the tests pass'], known, {'done_when': []}))
