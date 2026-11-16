"""Practice 94 (owner 16 Nov 2026): Practices 86 and 87 applied cleanly but read "partly applied" (two insertions above the same line; a
rename whose old name a new wrapper still uses), so HB never committed 87. And git commits whole files, so 86's commit quietly carried
earlier uncommitted work in the same file. Now a set HB applied reads "applied", and the commit message names any carried edits."""
import json
import subprocess

from core import hb_change_sets as cs


def _save(root, step, edits, new_files=None):
    d = root / 'runtime' / 'change_sets' / 'steps' / step
    d.mkdir(parents=True)
    (d / 'change_set.json').write_text(json.dumps({'step_id': step, 'why': 'w', 'edits': edits, 'new_files': new_files or {}, 'test': {}}))


def test_practice_94_two_insertions_above_the_same_line_both_read_applied(tmp_path):
    (tmp_path / 'm.py').write_text('def permission_excuse():\n    return 1\n')
    anchor = 'def permission_excuse():\n'
    _save(tmp_path, 'S-A', [{'path': 'm.py', 'old': anchor, 'new': 'A = 1\n\n\n' + anchor}])
    _save(tmp_path, 'S-B', [{'path': 'm.py', 'old': anchor, 'new': 'B = 2\n\n\n' + anchor}])
    assert cs.apply('S-A', tmp_path)['state'] == 'applied'
    assert cs.apply('S-B', tmp_path)['state'] == 'applied'
    assert cs.status('S-A', tmp_path)['state'] == 'applied' and cs.status('S-B', tmp_path)['state'] == 'applied'


def test_practice_94_a_rename_whose_old_name_is_reused_reads_applied(tmp_path):
    (tmp_path / 'g.py').write_text('def grounded(a):\n    return a\n\nEND = 1\n')
    _save(tmp_path, 'S-C', [{'path': 'g.py', 'old': 'def grounded(a):\n', 'new': 'def _grounded(a):\n'},
                            {'path': 'g.py', 'old': 'END = 1\n', 'new': 'def grounded(a):\n    return _grounded(a)\n\nEND = 1\n'}])
    assert cs.status('S-C', tmp_path)['state'] == 'not applied'
    assert cs.apply('S-C', tmp_path)['state'] == 'applied'
    assert cs.status('S-C', tmp_path)['state'] == 'applied'
    cs.revert('S-C', tmp_path)
    assert cs.status('S-C', tmp_path)['state'] != 'applied'


def test_practice_94_the_commit_names_edits_it_carries(tmp_path, monkeypatch):
    for k, v in {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}.items():
        monkeypatch.setenv(k, v)
    git = lambda *a: subprocess.run(['git', '-C', str(tmp_path), *a], capture_output=True, text=True, check=True)
    git('init', '-q')
    (tmp_path / '.gitignore').write_text('runtime/\n')
    (tmp_path / 'x.py').write_text('a = 1\nb = 2\n')
    git('add', '.'); git('commit', '-qm', 'base')
    (tmp_path / 'x.py').write_text('a = 1\nb = 2\nearlier = 3\n')          # someone's uncommitted work
    _save(tmp_path, 'S-D', [{'path': 'x.py', 'old': 'a = 1\n', 'new': 'a = 10\n'}])
    cs.apply('S-D', tmp_path)
    out = cs.commit('S-D', 'Practice 94 check', tmp_path)
    assert out['state'] == 'committed'
    assert 'Also carries earlier uncommitted edits in: x.py' in git('log', '-1', '--format=%B').stdout
