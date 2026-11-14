"""Owner 13 Nov: system cleanup tool. Moves are logged and undoable; used or protected paths are refused; nothing is deleted."""
import pytest
from core import hb_layout


def test_move_and_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(hb_layout, 'LOG', tmp_path / 'runtime/change_sets/layout/moves.jsonl')
    (tmp_path / 'core').mkdir(); (tmp_path / 'old_notes.txt').write_text('x')
    assert hb_layout.move('old_notes.txt', 'archive/old_notes.txt', tmp_path)['to'] == 'archive/old_notes.txt'
    assert (tmp_path / 'archive/old_notes.txt').exists() and not (tmp_path / 'old_notes.txt').exists()
    assert hb_layout.undo(tmp_path) == {'restored': 'old_notes.txt'} and (tmp_path / 'old_notes.txt').exists()


def test_used_and_protected_paths_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(hb_layout, 'LOG', tmp_path / 'log.jsonl')
    (tmp_path / 'core').mkdir(); (tmp_path / 'helper.py').write_text('x=1')
    (tmp_path / 'core/a.py').write_text('import helper\n')
    with pytest.raises(PermissionError, match='still used'):
        hb_layout.move('helper.py', 'archive/helper.py', tmp_path)
    with pytest.raises(PermissionError):
        hb_layout.move('swarm_memory.db', 'archive/x.db', tmp_path)
    with pytest.raises(PermissionError):
        hb_layout.move('../etc', 'archive/etc', tmp_path)
