"""Practice 52 (15 Nov): APEX applied practice 47 twice - every line it inserted was doubled. An insertion now counts as applied,
so a second apply changes nothing; the doubled lines are gone."""
from pathlib import Path
import core.hb_change_sets as cs

ROOT = Path(__file__).resolve().parents[1]


def make(tmp_path, edits):
    (tmp_path / 'core').mkdir()
    (tmp_path / 'core/a.py').write_text('x = 1\ny = 2\n')
    d = tmp_path / 'runtime/change_sets/steps/S-T'
    d.mkdir(parents=True)
    import json
    (d / 'change_set.json').write_text(json.dumps({'step_id': 'S-T', 'why': 'w', 'edits': edits, 'new_files': {}, 'test': {'tests': []}}))


def test_practice_52_an_insertion_is_applied_once(tmp_path):
    make(tmp_path, [{'path': 'core/a.py', 'old': 'x = 1\n', 'new': 'x = 1\nz = 3\n'}])
    assert cs.status('S-T', tmp_path)['state'] == 'not applied'
    cs.apply('S-T', tmp_path)
    assert (tmp_path / 'core/a.py').read_text() == 'x = 1\nz = 3\ny = 2\n'
    assert cs.status('S-T', tmp_path)['state'] == 'applied'
    assert cs.apply('S-T', tmp_path)['state'] == 'ALREADY APPLIED'
    assert (tmp_path / 'core/a.py').read_text() == 'x = 1\nz = 3\ny = 2\n'


def test_practice_52_a_replacement_still_works(tmp_path):
    make(tmp_path, [{'path': 'core/a.py', 'old': 'y = 2\n', 'new': 'y = 5\n'}, {'path': 'core/a.py', 'old': 'x = 1\n', 'new': 'x = 1\nz = 3\n'}])
    cs.apply('S-T', tmp_path)
    assert (tmp_path / 'core/a.py').read_text() == 'x = 1\nz = 3\ny = 5\n' and cs.status('S-T', tmp_path)['state'] == 'applied'


def test_practice_52_doubled_lines_of_practice_47_are_gone():
    commands = (ROOT / 'core/hb_commands.py').read_text()
    assert commands.count("('today', '/today'") == 1 and commands.count("if cmd == 'today'") == 1 and commands.count("if command == 'today'") == 1
    assert (ROOT / 'core/peer_coordination.py').read_text().count('grounding_tick(conn)') == 1
    assert (ROOT / 'frontend/templates/terminal_base.html').read_text().count('hb-day-anchor.js') == 1
