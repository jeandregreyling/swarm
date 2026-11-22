"""Practice 245: runtime/checks and runtime/claude_helpers are readable; the rest of runtime/ is not."""
import pytest

from core.apex_tools import ReadOnlyRepository


def test_code_folders_in_runtime_are_open_and_state_is_closed(tmp_path):
    r = ReadOnlyRepository(tmp_path)
    for rel in ('runtime/checks/x.py', 'runtime/claude_helpers/y.py'):
        assert r._path(rel) == (tmp_path / rel).resolve() or r._path(rel)
    for rel in ('runtime/change_sets/s.json', 'runtime/records/a.json', 'runtime/maintenance.json', 'runtime/checksx/z.py', '.git/config'):
        with pytest.raises(PermissionError, match='Protected repository path'):
            r._path(rel)
