"""Practice 34 (owner 14 Nov): a missing file comes back with the closest real paths, so APEX stops repeating guesses."""
from core.apex_paths import did_you_mean, not_found

TRACKED = {'agents/seven/does.py', 'core/hb_rename.py', 'core/hb_agents.py', 'tests/test_does_rename.py'}


def test_practice_34_renamed_file_is_suggested():
    assert did_you_mean('agents/seven/deos.py', TRACKED)[0] == 'agents/seven/does.py'
    msg = not_found('agents/seven/deos.py', TRACKED)
    assert 'Did you mean: agents/seven/does.py' in msg and 'do not retry' in msg


def test_practice_34_same_name_in_another_folder_is_suggested():
    assert 'core/hb_agents.py' in did_you_mean('hb_agents.py', TRACKED)


def test_practice_34_nothing_close_keeps_the_old_advice():
    assert 'Use list_files or grep_repo' in not_found('core/DEOS_teacher_compiler.py', TRACKED)


def test_practice_34_apex_tools_uses_it():
    from pathlib import Path
    import core.apex_tools as t
    assert 'not_found(relative, tracked)' in Path(t.__file__).read_text()
