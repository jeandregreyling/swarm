"""Practice 269: studio_proposal on JD's phone turns, never for guests."""
import inspect

from core import hb_channels


def test_phone_turn_routes_studio_proposal_for_owner_only():
    src = inspect.getsource(hb_channels._answer_only)
    assert "if tool == 'studio_proposal' and not _guest_turn():" in src
    assert "propose(conn, 'apex', args, None)" in src and 'call studio_proposal with title' in src
