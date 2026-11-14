"""Owner 14 Nov: Claude Code prepares and tests each step's change; APEX shows, applies (no copying) and tests it."""
import json
import subprocess
import sys

import pytest

from core import hb_change_sets as cs


def _repo(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'mod.py').write_text('def value():\n    return 1\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_mod.py').write_text('import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n'
                                                    'from pkg.mod import value\n\ndef test_value_is_two():\n    assert value() == 2\n')
    return tmp_path


def _prepare(root, **kw):
    return cs.prepare('S-0000000001', why='value must be 2', edits=[{'path': 'pkg/mod.py', 'old': '    return 1', 'new': '    return 2'}],
                      new_files={'pkg/notes.md': 'value is 2\n'}, test={'tests': ['tests/test_mod.py']}, root=root, **kw)


def test_prepare_proves_the_set_and_leaves_the_files_as_they_were(tmp_path):
    root = _repo(tmp_path)
    saved = _prepare(root)
    assert saved['verified']['result'].startswith('1 passed')
    assert (root / 'pkg/mod.py').read_text().endswith('return 1\n') and not (root / 'pkg/notes.md').exists()
    assert '+    return 2' in (root / 'runtime/change_sets/steps/S-0000000001/patch.diff').read_text()


def test_a_set_that_fails_its_test_is_not_saved(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(AssertionError, match='does not pass its test'):
        cs.prepare('S-0000000001', why='x', edits=[{'path': 'pkg/mod.py', 'old': '    return 1', 'new': '    return 3'}],
                   test={'tests': ['tests/test_mod.py']}, root=root)
    assert cs.load('S-0000000001', root) is None and (root / 'pkg/mod.py').read_text().endswith('return 1\n')


def test_apex_shows_applies_and_cannot_apply_twice(tmp_path):
    root = _repo(tmp_path)
    _prepare(root)
    shown = cs.call({'action': 'show'}, 'S-0000000001', root)
    assert shown['files'] == ['pkg/mod.py', 'pkg/notes.md'] and '+    return 2' in shown['diff']
    assert cs.call({'action': 'status'}, 'S-0000000001', root)['state'] == 'not applied'
    done = cs.call({'action': 'apply'}, 'S-0000000001', root)
    assert done['state'] == 'applied' and set(done['files']) == {'pkg/mod.py', 'pkg/notes.md'} and 'run_tests' in done['next']
    assert subprocess.run([sys.executable, '-m', 'pytest', '-q', '-o', 'addopts=', 'tests/test_mod.py'], cwd=root).returncode == 0
    assert cs.call({'action': 'apply'}, 'S-0000000001', root)['state'] == 'ALREADY APPLIED'
    backup = root / done['before_copies'] / 'pkg/mod.py'
    assert backup.read_text().endswith('return 1\n')                            # before-copy kept


def test_drift_and_breakage_are_refused_without_changing_anything(tmp_path):
    root = _repo(tmp_path)
    _prepare(root)
    (root / 'pkg/mod.py').write_text('def value():\n    return 5\n')            # someone changed the file since
    with pytest.raises(ValueError, match='file changed since the set was prepared'):
        cs.call({'action': 'apply'}, 'S-0000000001', root)
    assert (root / 'pkg/mod.py').read_text().endswith('return 5\n') and not (root / 'pkg/notes.md').exists()
    with pytest.raises(ValueError, match='only action'):
        cs.call({'action': 'apply', 'path': 'x'}, 'S-0000000001', root)
    assert cs.call({'action': 'show'}, 'S-0000000002', root)['state'] == 'none'
