"""Tests for Fridays Windows game installs through Bottles."""
import sqlite3
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / 'utils'))

from fridays import game_installer as gi  # noqa: E402

ISO_NAME = 'Warcraft 3 The Frozen Throne v1.29.iso'


@pytest.fixture
def env(tmp_path, monkeypatch):
    downloads = tmp_path / 'Downloads'
    bottles = tmp_path / 'bottles'
    bottle = bottles / 'Fridays'
    (bottle / 'drive_c' / 'windows').mkdir(parents=True)
    (bottle / 'bottle.yml').write_text('Name: Fridays\n')
    downloads.mkdir()
    (downloads / ISO_NAME).write_bytes(b'iso')
    monkeypatch.setattr(gi, 'DOWNLOADS', downloads)
    monkeypatch.setattr(gi, 'STAGING', downloads / '.fridays-staging')
    monkeypatch.setattr(gi, 'BOTTLES_ROOT', bottles)
    monkeypatch.setattr(gi, 'STATE_FILE', tmp_path / 'runtime' / 'game_installs.json')

    db_path = tmp_path / 'hive.db'
    conn = sqlite3.connect(db_path)
    conn.execute('CREATE TABLE work_proposals (proposal_id TEXT, agent TEXT, status TEXT, title TEXT, description TEXT)')
    conn.execute('CREATE TABLE governance_log (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT, '
                 'old_status TEXT, new_status TEXT, agent TEXT, actor TEXT, note TEXT)')
    conn.commit()
    conn.close()

    def get_connection():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setitem(sys.modules, 'database', types.SimpleNamespace(get_connection=get_connection))
    return types.SimpleNamespace(downloads=downloads, bottle=bottle, db=db_path, tmp=tmp_path)


def _proposal(env, pid='WP-1', agent='gemma', status='approved', actor='ghost', title=f'Install {ISO_NAME}'):
    conn = sqlite3.connect(env.db)
    conn.execute('INSERT INTO work_proposals VALUES (?,?,?,?,?)', (pid, agent, status, title, ''))
    if actor:
        conn.execute("INSERT INTO governance_log (proposal_id, old_status, new_status, agent, actor) "
                     "VALUES (?, 'pending', 'approved', ?, ?)", (pid, agent, actor))
    conn.commit()
    conn.close()


# ── Source and bottle validation ──────────────────────────────────────────────

def test_resolve_source_accepts_download_with_spaces(env):
    assert gi.resolve_source(ISO_NAME) == (env.downloads / ISO_NAME).resolve()


@pytest.mark.parametrize('bad', ['../hive.db', '/etc/passwd', 'missing.iso'])
def test_resolve_source_rejects_outside_or_missing(env, bad):
    with pytest.raises(ValueError):
        gi.resolve_source(bad)


def test_resolve_source_rejects_symlink_escape_and_other_types(env):
    outside = env.tmp / 'evil.exe'
    outside.write_bytes(b'x')
    (env.downloads / 'link.exe').symlink_to(outside)
    (env.downloads / 'notes.txt').write_text('x')
    with pytest.raises(ValueError):
        gi.resolve_source('link.exe')
    with pytest.raises(ValueError):
        gi.resolve_source('notes.txt')


def test_check_bottle_requires_existing_safe_name(env):
    assert gi.check_bottle(None)[0] == 'Fridays'
    for bad in ('Missing', '../Fridays', '.'):
        with pytest.raises(ValueError):
            gi.check_bottle(bad)


# ── Ghost approval gate ───────────────────────────────────────────────────────

def test_ghost_approved_proposal_naming_file_passes(env):
    _proposal(env)
    assert gi.require_ghost_approval('WP-1', 'gemma', ISO_NAME) == ''


@pytest.mark.parametrize('kwargs, caller, fragment', [
    ({'actor': 'duck'}, 'gemma', 'no Ghost approval'),
    ({'actor': None}, 'gemma', 'no Ghost approval'),
    ({'status': 'pending'}, 'gemma', 'Ghost must approve'),
    ({'title': 'Install a game'}, 'gemma', 'must name the installer'),
    ({}, 'qwen', 'belongs to gemma'),
    ({}, 'ghost', 'belongs to gemma'),
])
def test_approval_gate_rejects(env, kwargs, caller, fragment):
    _proposal(env, **kwargs)
    assert fragment in gi.require_ghost_approval('WP-1', caller, ISO_NAME)


def test_approval_gate_reports_missing_governance_table(env):
    conn = sqlite3.connect(env.db)
    conn.execute('DROP TABLE governance_log')
    conn.commit()
    conn.close()
    _proposal(env, actor=None)
    assert 'could not be verified' in gi.require_ghost_approval('WP-1', 'gemma', ISO_NAME)


# ── ISO staging and setup discovery ───────────────────────────────────────────

def test_stage_iso_extracts_once_and_reuses(env, monkeypatch):
    calls = []

    def fake_7z(cmd, **_):
        calls.append(cmd)
        out = Path(cmd[3][2:])
        out.mkdir(parents=True)
        (out / 'setup.exe').write_bytes(b'MZ')
        return subprocess.CompletedProcess(cmd, 0, '', '')

    monkeypatch.setattr(gi.shutil, 'which', lambda _name: '/usr/bin/7z')
    source = env.downloads / ISO_NAME
    first = gi.stage_iso(source, runner=fake_7z)
    second = gi.stage_iso(source, runner=fake_7z)
    assert first == second and (first / 'setup.exe').is_file()
    assert len(calls) == 1 and calls[0][:3] == ['7z', 'x', '-y']
    assert gi.STAGING in first.parents

    other_dir = env.downloads / 'copy'
    other_dir.mkdir()
    other = other_dir / ISO_NAME
    other.write_bytes(b'iso')
    assert gi.stage_iso(other, runner=fake_7z) != first
    assert len(calls) == 2


def test_find_setup_uses_autorun_then_standard_names(tmp_path):
    (tmp_path / 'autorun.inf').write_text('[autorun]\nopen=Launcher.exe /x\nicon=a.ico\n')
    (tmp_path / 'Launcher.exe').write_bytes(b'MZ')
    (tmp_path / 'setup.exe').write_bytes(b'MZ')
    assert gi.find_setup(tmp_path).name == 'Launcher.exe'
    (tmp_path / 'autorun.inf').write_text('[autorun]\nopen=..\\..\\evil.exe\n')
    assert gi.find_setup(tmp_path).name == 'setup.exe'


def test_find_setup_errors_without_installer(tmp_path):
    (tmp_path / 'readme.txt').write_text('x')
    with pytest.raises(RuntimeError):
        gi.find_setup(tmp_path)


# ── Launch ────────────────────────────────────────────────────────────────────

def test_launch_uses_user_session_and_bottles_cli(tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen['cmd'], seen['env'] = cmd, kw['env']
        return subprocess.CompletedProcess(cmd, 0, '', '')

    setup = tmp_path / 'my games' / 'setup.exe'
    gi.launch_in_bottle('Fridays', setup, 'fridays-game-install-x', runner=fake_run)
    cmd = seen['cmd']
    assert cmd[:3] == ['systemd-run', '--user', '--collect']
    assert cmd[cmd.index('--') + 1:] == [*gi.BOTTLES_CLI, 'run', '-b', 'Fridays', '-e', str(setup)]
    assert seen['env']['DBUS_SESSION_BUS_ADDRESS']


def test_skill_game_install_requires_approval_before_launch(env, monkeypatch):
    monkeypatch.setattr(gi, 'launch_in_bottle', lambda *a, **k: pytest.fail('launched without approval'))
    _proposal(env, actor='duck')
    ok, out = gi.skill_game_install(f'WP-1 {ISO_NAME}', 'gemma')
    assert not ok and 'Ghost approval' in out


def test_skill_game_install_stages_launches_and_records(env, monkeypatch):
    _proposal(env)
    staged = gi.STAGING / 'x'
    staged.mkdir(parents=True)
    (staged / 'setup.exe').write_bytes(b'MZ')
    launched = []
    monkeypatch.setattr(gi, 'stage_iso', lambda _source: staged)
    monkeypatch.setattr(gi, 'launch_in_bottle', lambda bottle, setup, unit: launched.append((bottle, setup, unit)))
    ok, out = gi.skill_game_install(f'WP-1 {ISO_NAME}', 'gemma')
    assert ok, out
    assert launched[0][:2] == ('Fridays', (staged / 'setup.exe').resolve())
    job = gi._latest_job('WP-1')
    assert job['status'] == 'launched' and job['source_name'] == ISO_NAME
    assert 'not a finished install' in out


# ── Registration ──────────────────────────────────────────────────────────────

def _job(env, started):
    gi._save_job({'job_id': 'j1', 'proposal_id': 'WP-1', 'agent': 'gemma', 'bottle': 'Fridays',
                  'source_name': ISO_NAME, 'unit': 'u', 'started_at': started, 'status': 'launched'})


def test_find_game_executables_filters_old_and_helper_files(env):
    drive = env.bottle / 'drive_c'
    game = drive / 'Program Files (x86)' / 'Warcraft III'
    game.mkdir(parents=True)
    for name in ('Frozen Throne.exe', 'unins000.exe', 'vcredist_x86.exe'):
        (game / name).write_bytes(b'MZ' * 10)
    (drive / 'windows' / 'notepad.exe').write_bytes(b'MZ')
    found = gi.find_game_executables(env.bottle, time.time() - 60)
    assert [p.name for p in found] == ['Frozen Throne.exe']
    assert gi.find_game_executables(env.bottle, time.time() + 3600) == []


def test_register_adds_and_verifies_program(env, monkeypatch):
    _proposal(env)
    _job(env, time.time() - 60)
    exe = env.bottle / 'drive_c' / 'Games' / 'Warcraft III' / 'Frozen Throne.exe'
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'MZ')
    programs = []
    monkeypatch.setattr(gi, 'unit_state', lambda _unit: 'inactive')
    monkeypatch.setattr(gi, 'list_programs', lambda _bottle: list(programs))
    monkeypatch.setattr(gi, 'add_program', lambda b, n, p: programs.append(
        {'name': n, 'folder': str(p.parent), 'executable': p.name}))
    ok, out = gi.skill_game_register('WP-1 "Warcraft III"', 'gemma')
    assert ok, out
    assert programs == [{'name': 'Warcraft III', 'folder': str(exe.parent), 'executable': exe.name}]
    assert gi._latest_job('WP-1')['status'] == 'registered'


def test_register_waits_for_running_installer_and_asks_for_hint(env, monkeypatch):
    _proposal(env)
    _job(env, time.time() - 60)
    folder = env.bottle / 'drive_c' / 'Games'
    folder.mkdir(parents=True)
    (folder / 'war3.exe').write_bytes(b'MZ')
    (folder / 'World Editor.exe').write_bytes(b'MZ')
    monkeypatch.setattr(gi, 'unit_state', lambda _unit: 'active')
    ok, out = gi.skill_game_register('WP-1 Warcraft', 'gemma')
    assert not ok and 'still running' in out
    monkeypatch.setattr(gi, 'unit_state', lambda _unit: 'inactive')
    monkeypatch.setattr(gi, 'list_programs', lambda _bottle: [])
    ok, out = gi.skill_game_register('WP-1 Warcraft', 'gemma')
    assert not ok and 'exe=<hint>' in out


# ── Skill registry ────────────────────────────────────────────────────────────

def test_skills_registered_with_expected_trust():
    from fridays import skills
    for name, level in (('game_installers', 0), ('game_install', 1), ('game_register', 1)):
        assert skills.REGISTRY[name]['trust_level'] == level
        assert name in skills._HANDLERS
