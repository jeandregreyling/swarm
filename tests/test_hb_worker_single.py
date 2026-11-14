"""Practice 77 (audit 15 Nov): hummingbird-apex-peer restarted 36 times and hummingbird-codex-peer ended "failed" - each was the
second worker for its agent and crashed on the lock. The latecomer steps aside with exit 0."""
import fcntl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def test_practice_77_second_worker_steps_aside(tmp_path, monkeypatch, capsys):
    import hummingbird_peer_worker as w
    held = (tmp_path / 'hb-worker.lock').open('a')
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)                 # the first worker

    class API:
        def __init__(self, agent): pass
        def call(self, path, body=None): return {'principal': 'apex'}
    monkeypatch.setattr(w.agent_identity, 'directory', lambda agent: tmp_path)
    assert w.serve('apex', once=True, api_factory=API) is None       # no traceback, no SystemExit(1)
    assert 'Another HB worker for apex is already running' in capsys.readouterr().out
    assert not (tmp_path / 'hb-worker.sqlite').exists()              # it touched nothing
