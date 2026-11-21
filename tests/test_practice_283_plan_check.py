"""Practice 283: homework's plan check (Practice 282) on a real card - a module.function name is not a missing file, and 'run the test suite'
is vague (name the test file)."""
from core import hb_homework as hw

FACTS = {'files': [{'path': 'core/hb_roles.py'}], 'done_when': []}


def test_function_names_are_not_missing_files_and_the_test_suite_is_vague():
    probs = hw.plan_problems(['Implement the core/hb_roles.model_for_job function in core/hb_roles.py.',
                              'Verify the implementation by running the test suite.'], {'core/hb_roles.py'}, FACTS)
    assert not any('model_for_job' in p for p in probs)
    assert any('plan step 2 is vague' in p for p in probs)
    assert any('core/hb_nope.py' in p for p in hw.plan_problems(['fix core/hb_nope.py'], set(), FACTS))
