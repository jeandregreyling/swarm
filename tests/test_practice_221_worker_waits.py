"""Practice 221 (calm swarm 3/5): workers wait out an HB restart instead of crashing."""
import urllib.error

import pytest

from scripts import hummingbird_peer_worker as worker


class Flaky:
    def __init__(self, down):
        self.down, self.calls = down, []

    def call(self, path, body=None):
        self.calls.append(path)
        if self.down > 0:
            self.down -= 1
            raise urllib.error.URLError(ConnectionRefusedError(111, 'Connection refused'))
        return {'ok': True, 'principal': 'apex'}


def test_wait_for_hb_waits_until_hb_answers(monkeypatch):
    monkeypatch.setattr(worker.time, 'sleep', lambda s: None)
    api = Flaky(down=3)
    assert worker.wait_for_hb(api) is True and api.calls.count('/api/agent/v1/whoami') == 4


def test_an_http_error_means_hb_is_up():
    class Answers:
        def call(self, path, body=None):
            raise ValueError('apex: /api/agent/v1/whoami returned HTTP 500')
    assert worker.wait_for_hb(Answers()) is True


def test_wait_for_hb_gives_up_after_its_limit(monkeypatch):
    clock = iter(range(0, 10 ** 6, 100))
    monkeypatch.setattr(worker.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(worker.time, 'sleep', lambda s: None)
    assert worker.wait_for_hb(Flaky(down=10 ** 6), limit=300) is False


def test_calmly_tries_once_more_when_hb_is_back(monkeypatch):
    monkeypatch.setattr(worker.time, 'sleep', lambda s: None)
    seen = []

    def report(x):
        seen.append(x)
        if len(seen) == 1:
            raise urllib.error.URLError('HB restarting')
        return 'ok'
    assert worker.calmly(Flaky(down=0), report, 7) == 'ok' and seen == [7, 7]


def test_an_error_hb_answered_is_not_swallowed():
    def report():
        raise ValueError('apex: /api/agent/v1/progress returned HTTP 400')
    with pytest.raises(ValueError):
        worker.calmly(Flaky(down=0), report)

