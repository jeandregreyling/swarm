"""Practice 74 (owner 15 Nov): a paused task's running turn was never stopped (link vs real path), and Fred took over a chat line."""
import inspect
import os
import sqlite3
import core.hb_executions as x
import core.hb_task_manager as m
import core.hb_commands as cmds


def test_practice_74_a_link_and_its_target_are_the_same_file(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    (real / 'worker.py').write_text('x')
    os.symlink(real, tmp_path / 'link')
    assert x.same_file(tmp_path / 'link' / 'worker.py', real / 'worker.py') is True
    assert x.same_file(real / 'worker.py', real / 'other.py') is False
    assert 'same_file(args[1],expected)' in inspect.getsource(x.stop_held_executors)


def test_practice_74_fred_does_not_take_over_a_chat_line(monkeypatch):
    from core import hb_local_jobs, hb_model_switches
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT, created_at REAL)')
    monkeypatch.setattr(hb_model_switches, 'modes', lambda conn: {})
    monkeypatch.setattr(hb_local_jobs, 'ensure_schema', lambda conn: None)
    assert m.local_help(c, {'task_id': 'T-1', 'step_id': None, 'conversation_id': 1}).startswith('unavailable: a chat line with no Studio step')


def test_practice_74_pause_also_stops_the_running_turn(monkeypatch):
    monkeypatch.setattr(cmds, '_set_mode', lambda conn, task_id, mode, actor: f'{task_id} is now Off (paused).')
    after = []
    assert cmds.run(None, 1, 'pause', ['T-1'], 'jd', after) == 'T-1 is now Off (paused).'
    assert len(after) == 1 and callable(after[0])
    after2 = []
    cmds.run(None, 1, 'continue', ['T-1'], 'jd', after2)
    assert after2 == []
