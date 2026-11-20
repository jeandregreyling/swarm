"""Practice 183: the bug method teaches APEX to decide whether the code or the test is out of date."""
from core import hb_learning


def test_bugfix_method_has_the_stale_test_step():
    m = hb_learning.bugfix_method()
    assert 'Decide which side is out of date: the code or the test' in m
    assert 'that is not weakening a test' in m and 'never weaken a test' in m
