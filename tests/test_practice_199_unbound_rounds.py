"""Practice 199: HB rounds are not capped at four handoffs."""
from core import peer_bridge


def test_rounds_are_unbound():
    assert peer_bridge.MAX_PEER_CHAIN >= 1000
