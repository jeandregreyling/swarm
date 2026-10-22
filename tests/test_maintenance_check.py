import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from fridays import skills


@pytest.mark.parametrize('args', ['', 'all', 'skills -x', '../test.py', 'skills; uptime'])
def test_maintenance_check_rejects_unlisted_commands(args, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid suite must not start a process')

    monkeypatch.setattr(subprocess, 'run', unexpected)
    ok, output = skills._skill_maintenance_check(args, 'apex')
    assert not ok
    assert 'Usage:' in output


def test_maintenance_check_uses_fixed_argv_and_temporary_database(monkeypatch):
    seen = []

    def run(command, **kwargs):
        seen.append((command, kwargs))
        assert Path(kwargs['env']['SWARM_DB_PATH']).parent.is_dir()
        return SimpleNamespace(returncode=0, stdout='10 passed', stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    ok, output = skills._skill_maintenance_check('skills', 'apex')
    assert ok
    command, options = seen[0]
    project_python = Path(skills._SWARM_ROOT_STR).resolve() / (
        '.venv/Scripts/python.exe' if skills.os.name == 'nt' else '.venv/bin/python3'
    )
    assert command == [
        str(project_python) if project_python.is_file() else skills.sys.executable,
        '-m', 'pytest', '-q',
        'tests/test_skills_loop_local_agents.py', 'tests/test_maintenance_check.py',
    ]
    assert options['timeout'] == 120
    assert options.get('shell', False) is False
    assert not Path(options['env']['SWARM_DB_PATH']).parent.exists()
    assert 'Exit code: 0' in output and '10 passed' in output


@pytest.mark.parametrize('has_project_environment', [True, False])
def test_maintenance_interpreter_prefers_project_without_resolving_it(
        tmp_path, monkeypatch, has_project_environment):
    monkeypatch.setattr(skills, '_SWARM_ROOT_STR', str(tmp_path))
    for name in ('test_skills_loop_local_agents.py', 'test_maintenance_check.py'):
        target = tmp_path / 'tests' / name
        target.parent.mkdir(exist_ok=True)
        target.touch()
    project_python = tmp_path / (
        '.venv/Scripts/python.exe' if skills.os.name == 'nt' else '.venv/bin/python3'
    )
    if has_project_environment:
        project_python.parent.mkdir(parents=True)
        project_python.symlink_to(skills.sys.executable)

    def run(command, **kwargs):
        expected = str(project_python) if has_project_environment else skills.sys.executable
        assert command[0] == expected
        return SimpleNamespace(returncode=0, stdout='passed', stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    assert skills._skill_maintenance_check('skills', 'qwen')[0]


def test_maintenance_check_preserves_failed_exit_and_output(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stdout='1 failed', stderr='test failure'))
    ok, output = skills._skill_maintenance_check('interests', 'qwen')
    assert not ok
    assert 'Exit code: 1' in output and '1 failed' in output and 'test failure' in output


def test_interests_suite_executes_ui_identity_and_backend_contracts(monkeypatch):
    def run(command, **kwargs):
        assert command[4:] == [
            'tests/test_interests_provenance.py',
            'tests/test_y52_interests_cross_user_isolation.py',
            'tests/test_interest_identity_frontend.py',
        ]
        return SimpleNamespace(returncode=0, stdout='11 passed', stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    ok, output = skills._skill_maintenance_check('interests', 'qwen')
    assert ok and 'Exit code: 0' in output


def test_maintenance_check_reports_timeout(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 120)

    monkeypatch.setattr(subprocess, 'run', run)
    ok, output = skills._skill_maintenance_check('skills', 'apex')
    assert not ok
    assert 'timed out' in output and 'no pass recorded' in output


def test_maintenance_check_is_registered_and_seven_stays_read_only():
    from utils.local_runtime_policy import agent_skill_allowed

    assert skills._HANDLERS['maintenance_check'] is skills._skill_maintenance_check
    assert skills.REGISTRY['maintenance_check']['trust_level'] == 1
    assert not agent_skill_allowed('seven', 'maintenance_check')


def test_training_requires_receipts_not_correct_sounding_prose():
    from scripts.maintenance_training import verify_exercise

    assert not verify_exercise('apex', 'source', 'The default username is seven.')[0]
    assert not verify_exercise('apex', 'tests', 'The tests passed with exit code 0.')[0]
    assert not verify_exercise(
        'apex', 'tests',
        '[verification] failed\n\nExecution evidence:\n'
        '[skill:maintenance_check] OK\nExit code: 0',
    )[0]


def test_training_source_requires_receipt_and_teach_back():
    from scripts.maintenance_training import verify_exercise

    receipt = "\n\nExecution evidence:\n[skill:fs_readonly] OK\nusername = request.args.get('username') or 'seven'"
    assert verify_exercise('apex', 'source', 'The fallback is seven.' + receipt)[0]
    assert not verify_exercise('apex', 'source', 'The fallback is user.' + receipt)[0]


def test_training_lesson_verifies_persisted_bytes_and_fresh_recall(tmp_path, monkeypatch):
    from scripts import maintenance_training as training

    monkeypatch.setattr(training, 'ROOT', tmp_path)
    note = tmp_path / 'sandpits' / 'apex' / 'maintenance_training.txt'
    note.parent.mkdir(parents=True)
    note.write_text('Models use memory. Tool receipts prove actions. Ghost approves. Private memory stays private.')
    receipts = '\n\nExecution evidence:\n[skill:file_write] OK\nwritten\n\n[skill:file_read] OK\n' + note.read_text()
    assert training.verify_exercise('apex', 'lesson', 'Saved my lesson.' + receipts)[0]
    assert training.verify_exercise('apex', 'recall', 'Ghost must approve.' + receipts)[0]
    note.write_text('Different content')
    assert not training.verify_exercise('apex', 'lesson', 'Saved my lesson.' + receipts)[0]


def test_training_exercise_tools_are_narrow():
    from scripts.maintenance_training import exercise_spec

    assert exercise_spec('apex', 'source')[1] == {'fs_readonly'}
    assert exercise_spec('apex', 'safeguards')[1] == {'fs_readonly'}
    assert exercise_spec('apex', 'tests')[1] == {'maintenance_check'}
    assert exercise_spec('apex', 'lesson')[1] == {'file_write', 'file_read'}
    assert exercise_spec('apex', 'recall')[1] == {'file_read'}
    with pytest.raises(ValueError, match='Unknown exercise'):
        exercise_spec('apex', 'shell')
