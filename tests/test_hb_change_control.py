"""Practice 53 (owner 13 Nov): change control - a change set is reverted in one action, and committed locally (only its files) on Approve."""
import json
import subprocess
import core.hb_change_sets as cs
import core.hb_commands as cmds


def repo(tmp_path):
    git = lambda *a: subprocess.run(['git', '-C', str(tmp_path), *a], check=True, capture_output=True, text=True)
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    git('config', 'user.email', 'hb@localhost'); git('config', 'user.name', 'HB')
    (tmp_path / 'core').mkdir()
    (tmp_path / 'core/a.py').write_text('x = 1\n')
    (tmp_path / 'other.txt').write_text('before\n')
    git('add', '.'); git('commit', '-q', '-m', 'start')
    d = tmp_path / 'runtime/change_sets/steps/S-T'
    d.mkdir(parents=True)
    (d / 'change_set.json').write_text(json.dumps({'step_id': 'S-T', 'why': 'make x two', 'edits': [{'path': 'core/a.py', 'old': 'x = 1\n', 'new': 'x = 2\n'}],
                                                    'new_files': {'core/b.py': 'y = 1\n'}, 'test': {'tests': []}}))
    return git


def test_practice_53_revert_puts_every_file_back(tmp_path):
    repo(tmp_path)
    assert cs.revert('S-T', tmp_path)['state'] == 'nothing to revert'
    cs.apply('S-T', tmp_path)
    assert (tmp_path / 'core/a.py').read_text() == 'x = 2\n' and (tmp_path / 'core/b.py').is_file()
    r = cs.revert('S-T', tmp_path)
    assert r == {'state': 'reverted', 'restored': ['core/a.py'], 'removed': ['core/b.py']}
    assert (tmp_path / 'core/a.py').read_text() == 'x = 1\n' and not (tmp_path / 'core/b.py').exists()
    assert cs.record('S-T', tmp_path)['reverted']['restored'] == ['core/a.py']


def test_practice_53_commit_takes_only_the_change_set_files(tmp_path):
    git = repo(tmp_path)
    assert cs.commit('S-T', 'Practice X', tmp_path) == {'state': 'not applied'}
    cs.apply('S-T', tmp_path)
    (tmp_path / 'other.txt').write_text('someone else is editing this\n')
    done = cs.commit('S-T', 'Practice X', tmp_path)
    assert done['state'] == 'committed' and done['files'] == ['core/a.py', 'core/b.py']
    assert git('show', '--name-only', '--format=%s', 'HEAD').stdout.split() [:5] == ['HB', 'change', 'set', 'S-T:', 'Practice']
    assert sorted(git('show', '--name-only', '--format=', 'HEAD').stdout.split()) == ['core/a.py', 'core/b.py']
    assert ' M other.txt' in git('status', '--short').stdout                     # the other edit is left alone, uncommitted
    assert cs.commit('S-T', 'Practice X', tmp_path)['state'] == 'nothing to commit'
    assert cs.record('S-T', tmp_path)['commit']['commit'] == done['commit']


def test_practice_53_git_lock_is_respected(tmp_path):
    repo(tmp_path)
    cs.apply('S-T', tmp_path)
    (tmp_path / '.git/index.lock').write_text('')
    assert cs.commit('S-T', 'x', tmp_path)['state'] == 'git locked'


def test_practice_53_commands():
    assert {'revert', 'changes'} <= set(cmds.NAMES)
    assert cmds.parse('revert s-0123456789') == ('revert', ['S-0123456789'])
    assert cmds.parse('changes S-0123456789') == ('changes', ['S-0123456789'])
    import inspect
    assert 'hb_change_sets.commit(step_id' in inspect.getsource(cmds.accept_step)
