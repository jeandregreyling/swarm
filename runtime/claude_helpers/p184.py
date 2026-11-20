"""Prepare Practice 184: old modules stop putting the retired root /home/seven/swarm on sys.path (the test-isolation bug)."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
OLD = "sys.path.insert(0, '/home/seven/swarm')"
NOTE = "  # backlog sweep 20 Nov: the repo root, not the retired root"
edits = []
for path, up in (('lib/system/system_clock.py', 2), ('lib/system/logging_bridge.py', 2), ('lib/system/monitor.py', 2),
                 ('fridays/browser_agent.py', 1), ('fridays/file_agent.py', 1)):
    edits.append({'path': path, 'old': OLD, 'new': f"sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[{up}])){NOTE}"})
edits.append({'path': 'fridays/telegram_bot.py', 'old': """sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/agents/ghost')""", 'new': """_REPO = __import__('pathlib').Path(__file__).resolve().parents[1]{note}
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / 'utils'))
sys.path.insert(0, str(_REPO / 'core' / 'pipeline'))
sys.path.insert(0, str(_REPO / 'agents' / 'ghost'))""".replace('{note}', NOTE)})

edits.append({'path': 'core/capability_packs/bugfix.method.v1.json', 'old': 'a renamed file (watchdog_deos -> watchdog_does)',
              'new': "a file renamed in the DOES rename that a course page still named"})   # Practice 183's lesson broke the rename check

test = '''"""Practice 184: no module puts the retired root /home/seven/swarm on sys.path."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _adds_retired_root(text):
    return any(('sys.path.insert' in line or 'sys.path.append' in line) and '/home/seven/swarm' in line
               and not line.strip().startswith('#') for line in text.splitlines())


def test_no_module_adds_the_retired_root():
    found = [str(p.relative_to(ROOT)) for d in ('core', 'frontend', 'lib', 'utils', 'fridays', 'agents', 'scripts')
             for p in (ROOT / d).rglob('*.py') if _adds_retired_root(p.read_text(errors='ignore'))]
    assert found == []


def test_importing_the_web_routes_keeps_the_retired_root_off_sys_path():
    code = ("import sys; sys.path[:0] = [%r, %r]; import frontend.blueprints.peer_bridge; "
            "print('/home/seven/swarm' in sys.path)") % (str(ROOT), str(ROOT / 'frontend'))
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.stdout.strip().splitlines()[-1] == 'False', out.stderr[-800:]
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("Backlog sweep 20 Nov - Bug: test isolation. Importing the web routes put the retired root /home/seven/swarm on "
                            "sys.path three times (lib/system/system_clock.py, logging_bridge.py, monitor.py, fridays/browser_agent.py, "
                            "file_agent.py, telegram_bot.py hard-coded it); test_shell_whitelist_behavior removed one copy and failed after "
                            "test_hb_peer_control. Each now uses the repo root from its own file location."),
                 edits=edits, new_files={'tests/test_practice_184_retired_root.py': test},
                 test={'tests': ['tests/test_practice_184_retired_root.py', 'tests/test_hb_peer_control.py', 'tests/test_gpu_residency.py',
                                 'tests/test_apex_tiered_assistant.py', 'tests/test_hummingbird_gemini_peer.py',
                                 'tests/test_swarm_root_priority_files.py', 'tests/test_does_rename.py'], 'keyword': ''}, run=run)
print(out['verified'])
