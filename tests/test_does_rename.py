"""Owner 13 Nov: DEOS becomes DOES everywhere in HB. The rename tool (core/hb_rename.py) applies a reviewed mapping one file at a
time; these tests are the progress meter APEX works towards, practice by practice."""
import json
from pathlib import Path

import pytest

from core import hb_rename

ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path, files):
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return tmp_path


def test_rules_rename_identifiers_and_text_but_not_videos_or_kept_lines():
    text = ('from utils.watchdog_deos import run_deos_cycle_summary\nx = "\\nDEOS_STATUS: done"\nclass DEOSTeacherPayload: pass\n'
            'promo = "launch videos"\nnote = "DOES replaces DEOS"  # kept\ntag = "watchdog:deos"\n')
    out = hb_rename.rewrite(text)
    assert 'utils.watchdog_does import run_does_cycle_summary' in out and 'DOES_STATUS' in out and 'DOESTeacherPayload' in out
    assert 'launch videos' in out and 'DOES replaces DEOS' in out and 'watchdog:does' in out


def test_apply_checks_saves_a_before_copy_and_refuses_hand_edit_files(tmp_path):
    root = _repo(tmp_path, {'core/x.py': 'DEOS = 1\n', 'core/bad.py': 'x = 1\n'})
    result = hb_rename.apply('core/x.py', root)
    assert result['lines_changed'] == 1 and (root / 'core/x.py').read_text() == 'DOES = 1\n'
    assert (root / result['before_copy']).read_text() == 'DEOS = 1\n'
    with pytest.raises(PermissionError):
        hb_rename.apply('utils/config.py', root)
    with pytest.raises(PermissionError):
        hb_rename.apply('../etc/passwd.py', root)


def test_move_leaves_a_working_alias_until_nothing_uses_the_old_name(tmp_path, monkeypatch):
    root = _repo(tmp_path, {'utils/__init__.py': '', 'utils/watchdog_deos.py': 'def run_deos_cycle_summary():\n    return "DEOS"\n',
                            'fridays/task_runner.py': 'from utils.watchdog_deos import run_deos_cycle_summary\n'})
    assert hb_rename.move('utils/watchdog_deos.py', root)['old_path'] == 'temporary alias'
    import sys
    for name in [m for m in list(sys.modules) if m == 'utils' or m.startswith('utils.')]:
        monkeypatch.delitem(sys.modules, name)          # restored after the test, so the real utils package is not shadowed
    monkeypatch.syspath_prepend(str(root))
    import importlib
    old = importlib.import_module('utils.watchdog_deos')
    assert old.run_does_cycle_summary() == 'DOES'
    with pytest.raises(ValueError, match='still used'):
        hb_rename.remove_alias('utils/watchdog_deos.py', root)
    hb_rename.apply('fridays/task_runner.py', root)
    assert hb_rename.remove_alias('utils/watchdog_deos.py', root) == {'removed_alias': 'utils/watchdog_deos.py'}
    for name, module in list(sys.modules.items()):      # drop the temporary package so later tests import the real utils
        if (name == 'utils' or name.startswith('utils.')) and str(getattr(module, '__file__', '') or '').startswith(str(root)):
            del sys.modules[name]


def test_does_rename_is_an_apex_tool_with_a_schema():
    from core.hb_agent_tools import WRITE_TOOLS
    from core.apex_tools import TOOL_SCHEMAS, _REQUIRED_ARGUMENTS
    from core.hb_task_manager import EXTRA_TOOLS
    assert 'does_rename' in WRITE_TOOLS and 'does_rename' in EXTRA_TOOLS
    assert set(TOOL_SCHEMAS['does_rename']) == {'action', 'path'} and _REQUIRED_ARGUMENTS['does_rename'] == ['action']


def _left(prefixes):
    return [r for r in hb_rename.remaining() if r[0].startswith(prefixes) and r[0] not in hb_rename.pack()['manual']]


def test_rename_1_moves_are_done():
    assert [a for a, b in hb_rename.pack()['moves'] if not (ROOT / b).exists()] == []


def test_rename_2_core_is_clean():
    assert _left(('core/',)) == []


def test_rename_3_utils_scripts_frontend_are_clean():
    assert _left(('utils/', 'scripts/', 'frontend/')) == []


def test_rename_4_agents_fridays_tests_are_clean():
    # agents/seven/seven_agent.py is DOES rename 6 (hand edits first), not this step (14 Nov: rename 4 could not pass without it)
    later = set(hb_rename.pack().get('manual_first', {}))
    assert [r for r in _left(('agents/', 'fridays/', 'tests/')) if r[0] not in later] == []


def test_rename_5_meaning_is_do_operate_execute_sustain():
    seat = json.loads((ROOT / 'core/capability_packs/hummingbird.apex-seat.v1.json').read_text())
    text = json.dumps(seat)
    assert 'Do, Operate, Execute, Sustain' in text and 'DEOS' not in text
    assert 'Do, Operate, Execute, Sustain' in (ROOT / 'utils/config.py').read_text()
    assert 'do, operate, execute, sustain' in (ROOT / 'fridays/task_runner.py').read_text()


def test_rename_6_seven_is_clean():
    assert [r for r in hb_rename.remaining() if r[0] == 'agents/seven/seven_agent.py'] == []


def test_rename_7_nothing_left_and_no_aliases():
    assert hb_rename.remaining() == []
    aliases = [a for a, b in hb_rename.pack()['moves'] if (ROOT / a).exists()]
    assert aliases == []


def test_seven_triggers_must_be_patched_by_hand_first(tmp_path):
    root = _repo(tmp_path, {'agents/seven/seven_agent.py': "def f(cmd):\n    if cmd in ('deos', 'proof', 'prove'):\n        x = 'DEOS'\n"})
    with pytest.raises(PermissionError, match='by hand first'):
        hb_rename.apply('agents/seven/seven_agent.py', root)
    (root / 'agents/seven/seven_agent.py').write_text("def f(cmd):\n    if cmd in ('does', 'proof', 'prove'):\n        x = 'DEOS'\n")
    assert hb_rename.apply('agents/seven/seven_agent.py', root)['lines_changed'] == 1


def test_tool_actions_are_allowed_by_the_answer_format():
    """13 Nov: the shared 'action' argument only allowed pause/resume, so APEX could never send move (it was forced to 'resume')."""
    from core.apex_tools import _call_schema
    for tool, action in (('does_rename', 'move'), ('does_rename', 'apply'), ('layout', 'inventory'), ('layout', 'move')):
        assert action in _call_schema(tool)['properties']['arguments']['properties']['action']['enum']


def test_tool_apply_says_what_is_still_left_in_the_folder(tmp_path, monkeypatch):
    """Owner 14 Nov: APEX looped re-applying finished files; the tool now names what is left and what to do next."""
    from core import hb_rename
    monkeypatch.setattr(hb_rename, 'remaining', lambda *a, **k: [('core/a.py', 1, 'DEOS'), ('core/b.py', 3, 'DEOS'), ('utils/c.py', 1, 'DEOS')])
    monkeypatch.setattr(hb_rename, 'apply', lambda path, root=None: {'path': path, 'lines_changed': 0, 'note': 'nothing left to rename in this file'})
    out = hb_rename.call({'action': 'apply', 'path': 'core/done.py'})
    assert out['still_to_rename_in_core/'] == ['core/a.py', 'core/b.py'] and out['next'].startswith('apply core/a.py next.')
    monkeypatch.setattr(hb_rename, 'remaining', lambda *a, **k: [])
    assert hb_rename.call({'action': 'apply', 'path': 'core/done.py'})['next'] == 'core/ is clean and nothing is left anywhere: run the step test now.'
    monkeypatch.setattr(hb_rename, 'remaining', lambda *a, **k: [('tests/t.py', 1, 'DEOS')])
    assert 'Still DEOS in other folders: tests/t.py' in hb_rename.call({'action': 'apply', 'path': 'agents/x.py'})['next']
