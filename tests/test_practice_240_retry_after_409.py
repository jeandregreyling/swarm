"""Practice 240: the instructions-changed 409 tells APEX to read task_context once and repeat the same call."""
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / 'frontend/blueprints/agent_identity.py').read_text()


def test_the_409_says_read_once_then_repeat_the_same_call():
    line = next(l for l in SRC.splitlines() if 'Task instructions changed' in l)
    assert 'PeerError(409' in line and 'call task_context ONCE' in line and 'repeat this exact {tool} call' in line
    assert 'Do not end the turn without retrying it' in line
