"""Practice 255: run_tests and ask_instructor on JD's phone turns; never for guests."""
import inspect

from core import hb_channels


def test_phone_turn_has_tests_and_instructor_for_owner_only():
    src = inspect.getsource(hb_channels._answer_only)
    assert 'test_handler=None if _guest_turn() else _run_tests' in src
    assert "if tool == 'ask_instructor' and not _guest_turn():" in src
    assert 'peer_bridge.request_help(conn, 2845' in src and 'ask_instructor {' in src
