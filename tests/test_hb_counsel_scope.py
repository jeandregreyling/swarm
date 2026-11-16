"""Practice 37 (owner 14 Nov): the counsel scopes steps whose Done-when has nothing runnable, and runs on the CPU without waiting
for APEX's GPU queue to empty."""
from pathlib import Path
from core import hb_counsel as hc


def test_practice_37_prose_done_when_is_counsel_work():
    assert not hc._runnable('Done when: Create a detailed spec and scope the review items works')
    assert hc._runnable('Done when: python -m pytest tests/test_x.py passes')
    src = Path(hc.__file__).read_text()
    assert "its Done when has no check APEX can run" in src


def test_practice_37_counsel_does_not_wait_for_the_gpu_queue():
    src = Path(hc.__file__).read_text()
    i = src.index('def _can_run')
    assert 'next_ready' not in src[i:i + 900]
