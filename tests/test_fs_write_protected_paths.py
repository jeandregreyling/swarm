import pytest

from fridays import skills


@pytest.mark.parametrize('rel', ['swarm_memory.db', 'mind.db', 'swarm_memory.db-wal', '.env', '.venv/pyvenv.cfg', '.git/config'])
def test_write_skills_refuse_protected_paths(rel):
    for fn, args in (
        (skills._skill_fs_write, f'{rel} hello'),
        (skills._skill_fs_append, f'{rel}\n```\nx\n```'),
        (skills._skill_fs_insert_after, f'{rel}\n```\na\n```\n```\nb\n```'),
        (skills._skill_fs_patch, f'{rel}\n```\na\n```\n```\nb\n```'),
        (skills._skill_fs_patch_lines, f'{rel} 1 1\n```\nx\n```'),
    ):
        ok, msg = fn(args, 'fred')
        assert ok is False and msg.startswith('Refused'), (fn.__name__, rel, msg)


def test_write_skill_still_writes_normal_files(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)
    ok, _ = skills._skill_fs_write('note.txt hello', 'fred')
    assert ok and (tmp_path / 'note.txt').read_text() == 'hello'
