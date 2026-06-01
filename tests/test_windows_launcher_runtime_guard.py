from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'windows' / 'launcher.py'
START_BAT = ROOT / 'windows' / 'start-fridays.bat'
TERMINAL = ROOT / 'frontend' / 'terminal.py'


def test_windows_launcher_reuses_existing_runtime_before_splash():
    src = LAUNCHER.read_text(encoding='utf-8')
    start = START_BAT.read_text(encoding='utf-8')
    terminal = TERMINAL.read_text(encoding='utf-8')

    assert 'def _is_healthy(timeout=2):' in src
    assert "payload.get('runtime_id')" in src
    assert "os.environ.get('FRIDAYS_RUNTIME_ID')" in src
    assert 'if _is_healthy():' in src
    assert "print(f'[Fridays] Reusing existing runtime on {_URL}')" in src
    assert "os.environ.setdefault('FRIDAYS_RUNTIME_ID', _runtime_default)" in src
    assert "set \"FRIDAYS_RUNTIME_ID=source:%ROOT%\"" in start
    assert "runtime_id" in terminal
    assert src.index('if _is_healthy():') < src.index('splash = _show_splash()')
