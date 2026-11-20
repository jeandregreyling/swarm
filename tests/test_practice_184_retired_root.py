"""Practice 184: no module puts the retired root /home/seven/swarm on sys.path."""
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
