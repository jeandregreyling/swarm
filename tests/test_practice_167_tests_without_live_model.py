"""Practice 167 (owner 18 Nov 2026): the APEX loop tests failed while the 27B played APEX (9 rounds, 600 s instead of 6 and 360)."""
from core import hb_apex_swap as s


def test_practice_167_tests_see_no_live_model():
    assert s.playing() is None and s.turn_rounds(6) == 6 and s.turn_seconds(360) == 360
