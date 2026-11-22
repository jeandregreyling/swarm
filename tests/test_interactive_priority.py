import os
import subprocess
import sys
import threading
import time
import json
import pytest

from core.hb_process_lock import ForegroundWaiter, ProcessLock, yield_to_foreground


def test_foreground_waiter_takes_turn_before_background_resumes(tmp_path, monkeypatch):
    monkeypatch.setenv('HUMMINGBIRD_LOCK_DIR', str(tmp_path))
    background = ProcessLock('apex-turn', tmp_path, timeout=5)
    assert background.acquire()
    entered, order = threading.Event(), []
    def foreground():
        turn = ProcessLock('apex-turn', tmp_path, timeout=5)
        with ForegroundWaiter(turn):
            entered.set()
            assert turn.acquire()
            try:
                order.append('foreground')
            finally:
                turn.release()
    thread = threading.Thread(target=foreground)
    thread.start()
    assert entered.wait(2)
    assert yield_to_foreground(background, lambda: order.append('yield'))
    order.append('background')
    background.release()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert order == ['yield', 'foreground', 'background']
    assert not ForegroundWaiter.pending(background)


def test_stale_marker_after_process_exit_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv('HUMMINGBIRD_LOCK_DIR', str(tmp_path))
    code = ('import os; from core.hb_process_lock import ProcessLock,ForegroundWaiter; '
            f't=ProcessLock("apex-turn",{str(tmp_path)!r}); '
            'w=ForegroundWaiter(t); w.__enter__(); os._exit(0)')
    subprocess.run([sys.executable, '-c', code], check=True, env=dict(os.environ))
    turn = ProcessLock('apex-turn', tmp_path)
    assert list(tmp_path.glob('*.foreground-*'))
    assert not ForegroundWaiter.pending(turn)
    assert not list(tmp_path.glob('*.foreground-*'))


def test_multiple_waiters_are_kept_independent(tmp_path, monkeypatch):
    monkeypatch.setenv('HUMMINGBIRD_LOCK_DIR', str(tmp_path))
    turn = ProcessLock('apex-turn', tmp_path)
    with ForegroundWaiter(turn):
        with ForegroundWaiter(turn):
            assert ForegroundWaiter.pending(turn)
        assert ForegroundWaiter.pending(turn)
    assert not ForegroundWaiter.pending(turn)


def test_cross_process_waiter_gets_turn_before_background_continues(tmp_path, monkeypatch):
    monkeypatch.setenv('HUMMINGBIRD_LOCK_DIR', str(tmp_path))
    turn = ProcessLock('apex-turn', tmp_path, timeout=5)
    assert turn.acquire()
    code = ('from core.hb_process_lock import ProcessLock,ForegroundWaiter; '
            f't=ProcessLock("apex-turn",{str(tmp_path)!r},timeout=5); '
            'w=ForegroundWaiter(t); w.__enter__(); print("waiting",flush=True); '
            'assert t.acquire(); print("acquired",flush=True); t.release(); w.__exit__(None,None,None)')
    child = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True, env=dict(os.environ))
    try:
        assert child.stdout.readline().strip() == 'waiting'
        assert yield_to_foreground(turn)
        assert child.stdout.readline().strip() == 'acquired'
        assert child.wait(timeout=5) == 0
    finally:
        turn.release()
        if child.poll() is None:
            child.kill(); child.wait()


def test_tool_loop_cooperates_only_after_receipt_is_saved():
    from core.apex_tools import run_apex_tools
    order = []
    outputs = iter([json.dumps({'tool_calls': [{'name': 'git_status', 'arguments': {}}], 'answer': ''}),
                    'The repository is clean.'])
    class Repo:
        def call(self, name, args):
            order.append('tool')
            return 'clean'
    def model(*_):
        order.append('model')
        return next(outputs), 1
    def receipt(_): order.append('receipt')
    result, _, receipts = run_apex_tools(model, [{'role': 'user', 'content': 'Inspect status'}], lambda: True,
                                         receipt, repository=Repo(), cooperate=lambda: order.append('checkpoint'))
    assert result and receipts
    assert order == ['checkpoint', 'model', 'tool', 'receipt', 'checkpoint', 'model']


def test_exception_clears_waiter_and_cancel_stops_next_model_round(tmp_path, monkeypatch):
    from core import agent_identity, hb_executions
    from core.apex_tools import run_apex_tools
    monkeypatch.setenv('HUMMINGBIRD_LOCK_DIR', str(tmp_path))
    turn = ProcessLock('apex-turn', tmp_path)
    with pytest.raises(ValueError):
        with ForegroundWaiter(turn):
            raise ValueError('client disconnected')
    assert not ForegroundWaiter.pending(turn)

    active, checkpoints, calls, emitted = [True], [], [], []
    monkeypatch.setattr(hb_executions, 'authorized', lambda _actor: active[0])
    class Repo:
        def call(self, *_): return 'clean'
    def model(*_):
        calls.append('model')
        return json.dumps({'tool_calls': [{'name': 'git_status', 'arguments': {}}], 'answer': ''}), 1
    def checkpoint():
        checkpoints.append(True)
        if len(checkpoints) == 2: active[0] = False
    token = agent_identity.CURRENT.set({'task_id': 'T-test'})
    try:
        with pytest.raises(PermissionError, match='Owner stopped'):
            run_apex_tools(model, [{'role': 'user', 'content': 'Inspect status'}], lambda: True,
                           emitted.append, repository=Repo(), cooperate=checkpoint)
    finally:
        agent_identity.CURRENT.reset(token)
    assert calls == ['model'] and len(emitted) == 1


def test_yield_reports_waiting_without_requeueing_the_live_job(monkeypatch):
    from contextlib import nullcontext
    from core import agent_identity, apex_routing, apex_tools, hb_process_lock
    from scripts import hummingbird_peer_worker as worker
    monkeypatch.setattr(apex_routing, 'choose_local_model',
                        lambda _: apex_routing.LocalRoute('test', 'general', 16384, 'test'))
    monkeypatch.setattr(agent_identity, 'execution', lambda *_a, **_k: nullcontext())
    def fake_yield(_gate, on_wait):
        on_wait()
        return True
    monkeypatch.setattr(hb_process_lock, 'yield_to_foreground', fake_yield)
    def run(*_a, **kwargs):
        kwargs['cooperate']()
        return 'done', 1, []
    monkeypatch.setattr(apex_tools, 'run_apex_tools', run)
    events = []
    class API:
        def call(self, path, body):
            events.append((path, body))
            return {'ok': True}
    worker.local_turn(API(), {'id': 42, 'conversation_id': 1, 'body': 'Inspect'}, [], [], gate=object())
    states = [body for path, body in events if path.endswith('/progress')]
    waiting = next(body for body in states if 'Waiting while APEX answers' in body['stage'])
    assert waiting['status'] == 'running'
    assert any(body['status'] == 'running' and 'Resuming' in body['stage'] for body in states)
    assert all(body['status'] != 'queued' for body in states)
