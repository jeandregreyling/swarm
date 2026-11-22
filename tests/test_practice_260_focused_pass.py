"""Practice 260: a passing focused run is labelled as a pass."""
import inspect

from core import hb_activity


def test_focused_pass_is_a_pass():
    src = inspect.getsource(hb_activity)
    assert "p.get('status') == 'passed' and p.get('exit_code') == 0" in src and "str(verdict).startswith('PASS')" in src
