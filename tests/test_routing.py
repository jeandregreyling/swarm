"""Tests for core.routing — Seven's deterministic router.

These lock the routing contract: explicit @mention > direct address > role
keyword > fallback. All decisions must be pure functions of their inputs;
none of these tests touch the DB.
"""
from core.routing import route, RouteDecision, SEVEN_ROLES, ROLE_KEYWORDS


def _routable(*names):
    return [{'name': n} for n in names]


def test_explicit_target_wins_when_routable():
    d = route('anything', routable_agents=_routable('ten', 'nine'),
              explicit_target='ten')
    assert d.target == 'ten'
    assert d.confidence == 1.0
    assert 'explicit' in d.rationale


def test_explicit_target_ignored_if_not_routable():
    """If caller passes a target that's disabled/silent-api, fall through."""
    d = route('hello there', routable_agents=_routable('duck'),
              explicit_target='scholar')
    # Should fall through to other rules — hello matches voice role
    assert d.target != 'scholar'


def test_at_mention_routes():
    d = route('@ten can you fix the regex', routable_agents=_routable('ten', 'gemma'))
    assert d.target == 'ten'
    assert d.confidence == 0.95
    assert d.category == 'coder'  # "fix the" keyword


def test_at_mention_ignored_if_not_routable():
    """An @mention for a disabled/silent-api agent falls through."""
    d = route('@scholar search for latest papers', routable_agents=_routable('gemma', 'llama'))
    assert d.target != 'scholar'
    assert d.category == 'researcher'  # "search for" keyword


def test_direct_address_form():
    d = route('Duck, can you review this?', routable_agents=_routable('duck', 'ten'))
    assert d.target == 'duck'
    assert d.confidence == 0.85
    assert d.category == 'auditor'  # "review" keyword


def test_role_keyword_routes_coder_to_ten():
    d = route('please refactor this function', routable_agents=_routable('ten', 'nine', 'gemma'))
    assert d.target == 'ten'
    assert d.category == 'coder'
    assert d.confidence == 0.6


def test_role_keyword_fallback_if_default_missing():
    """If 'ten' is not routable, coder should fall through to the next candidate."""
    d = route('please refactor this function', routable_agents=_routable('qwen', 'ghost_coder'))
    assert d.category == 'coder'
    # Next defaults after 'ten' are 'nine', 'ghost_coder', 'qwen' — ghost_coder is first routable
    assert d.target == 'ghost_coder'


def test_no_routable_agents_returns_none_target():
    d = route('anything', routable_agents=[])
    assert d.target is None
    assert d.confidence == 0.0


def test_sender_not_self_routed():
    """An agent's own mention of itself should not loop back."""
    d = route('@ten', sender='ten', routable_agents=_routable('ten', 'nine'))
    assert d.target != 'ten'


def test_voice_category_for_greetings():
    d = route('hello there', routable_agents=_routable('seven', 'duck', 'gemma'))
    assert d.category == 'voice'
    assert d.target == 'seven'


def test_decision_is_frozen_dataclass():
    """RouteDecision must be immutable — safe for audit logging."""
    d = RouteDecision(target='ten', category='coder', confidence=0.6,
                      rationale='test')
    import pytest
    with pytest.raises((AttributeError, Exception)):
        d.target = 'nine'  # type: ignore


def test_seven_roles_constant():
    assert len(SEVEN_ROLES) == 7
    assert set(SEVEN_ROLES) == set(ROLE_KEYWORDS.keys())
