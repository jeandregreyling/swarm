"""Practice 233: Fred's model is never copied into the next turn - only HB's task manager gives Fred a turn."""
import inspect

from core import hb_tasks, peer_bridge, peer_turns


def test_a_follow_up_turn_does_not_copy_freds_model():
    scope = {'allowed_tools': ['read_file', 'propose_patch'], 'preferred_local_model': 'fred-cpu:24b', 'owner_authorized_provider_probe': True}
    assert hb_tasks.inheritable(scope) == {'allowed_tools': ['read_file', 'propose_patch'], 'owner_authorized_provider_probe': True}


def test_continue_handoff_and_new_round_all_use_it():
    assert 'inheritable(inherited)' in inspect.getsource(hb_tasks.resume_by_owner)
    assert 'hb_tasks.inheritable(inherited)' in inspect.getsource(peer_bridge)
    assert "('preferred_local_model','owner_authorized_provider_probe')" not in inspect.getsource(peer_turns)
