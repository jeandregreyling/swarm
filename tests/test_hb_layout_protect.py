"""Practice 63 (owner 15 Nov): the layout tool never offers or moves live data and the root files tools expect in place."""
import pytest
import core.hb_layout as L


def test_practice_63_live_data_and_root_files_are_protected(tmp_path):
    for name in ('swarm_memory.db-wal', 'swarm_memory.db-shm', 'pyproject.toml', 'killswitch.sh', 'data/x.sqlite-wal'):
        with pytest.raises(PermissionError):
            L._rel(name, tmp_path)
    assert L._rel('archive/old.md', tmp_path)[0] == 'archive/old.md'


def test_practice_63_inventory_does_not_list_protected_entries(tmp_path, monkeypatch):
    for name in ('swarm_memory.db-wal', 'pyproject.toml', 'old_note.md'):
        (tmp_path / name).write_text('x')
    monkeypatch.setattr(L, '_references', lambda rel, root: [])
    assert [e['path'] for e in L.inventory(tmp_path)['entries']] == ['old_note.md']
