"""Practice 253: hb_tasks on JD's phone turns; never on a guest's."""
import inspect

from core import hb_channels


def test_phone_turn_offers_and_routes_hb_tasks_for_owner_only():
    src = inspect.getsource(hb_channels._answer_only)
    assert "if tool == 'hb_tasks' and not _guest_turn():" in src
    assert 'hb_tasks_tool(args)' in src and 'you also have the hb_tasks tool' in src


def test_guest_flag_is_read():
    from core import hb_guest
    tok = hb_guest.GUEST_TURN.set(True)
    try:
        assert hb_channels._guest_turn() is True
    finally:
        hb_guest.GUEST_TURN.reset(tok)
    assert hb_channels._guest_turn() is False


def test_owner_phone_turns_have_step_and_status_reads():
    src = inspect.getsource(hb_channels._answer_only)
    assert "if tool == 'alm_step_get' and not _guest_turn():" in src
    assert "if tool in ('backlog_list', 'runtime_status') and not _guest_turn():" in src
