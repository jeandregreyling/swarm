"""Practice 257: a phone work request is answered with its task, not an answer-only 'no permission' turn."""
import inspect

from core import hb_channels


def test_work_requests_get_their_task_line():
    src = inspect.getsource(hb_channels.work_one)
    assert "work = _work_task(job) if who == 'owner' else None" in src
    assert "runs as an HB task with APEX's full tools" in src


def test_no_task_means_a_normal_answer(monkeypatch):
    monkeypatch.setattr(hb_channels, '_connect', lambda: (_ for _ in ()).throw(RuntimeError('no db')))
    assert hb_channels._work_task({'message_id': 1}) is None
