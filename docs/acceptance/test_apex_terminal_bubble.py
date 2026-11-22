"""Acceptance test for the APEX terminal bubble step (owner 16 Nov 2026, the open part of S-9B9907AF1F "Terminal in main chat").
APEX copies this file to tests/test_apex_terminal_bubble.py in its change.

APEX's own commands reach main chat as raw receipts:
    [tool:terminal_run] succeeded (receipt 0b3b...)
    {"command": "df -h"}
    Filesystem  Size ...
Main chat shows them like JD's own terminal commands: "💻 APEX ran $ df -h", the output in a text block, and how it ended.
home-chat.js gets a function _hcTerminalReceipt(content) that returns that text (or null for anything else), and _hcAppendBubble
uses it for APEX's terminal_run receipts."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / 'frontend' / 'static' / 'js' / 'views' / 'home-chat.js'

HARNESS = r"""
const src = require('fs').readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('function _hcTerminalReceipt(');
if (start < 0) { console.log(JSON.stringify({missing: true})); process.exit(0); }
let depth = 0, end = start, seen = false;
for (let i = src.indexOf('{', start); i < src.length; i++) {
  if (src[i] === '{') { depth++; seen = true; }
  if (src[i] === '}') { depth--; if (seen && depth === 0) { end = i + 1; break; } }
}
eval(src.slice(start, end));
const cases = JSON.parse(process.argv[3]);
console.log(JSON.stringify(cases.map(c => _hcTerminalReceipt(c))));
"""

CASES = [
    '[tool:terminal_run] succeeded (receipt 0b3b5c4f)\n{"command": "df -h"}\nFilesystem  Size  Used\n/dev/nvme0n1p1  915G  579G',
    '[tool:terminal_run] failed (receipt e44f506d)\n{"command": "echo $?"}\nTerminal diagnostics require a single command without shell composition',
    '[tool:read_file] succeeded (receipt 1234)\n{"path": "x.py"}\nprint(1)',
    'Plain APEX answer, no receipt.',
]


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
def test_terminal_receipts_read_like_terminal_commands(tmp_path):
    h = tmp_path / 'h.js'
    h.write_text(HARNESS)
    out = subprocess.run(['node', str(h), str(JS), json.dumps(CASES)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got != {'missing': True}, 'home-chat.js has no _hcTerminalReceipt'
    ok, failed, other, plain = got
    assert ok.startswith('💻 APEX ran $ df -h\n') and '```text\nFilesystem  Size  Used' in ok and ok.rstrip().endswith('— completed')
    assert failed.startswith('💻 APEX ran $ echo $?\n') and 'single command' in failed and failed.rstrip().endswith('— refused or failed')
    assert other is None and plain is None


def test_apex_bubbles_use_it():
    src = JS.read_text()
    i = src.index('function _hcAppendBubble(')
    assert '_hcTerminalReceipt(' in src[i:i + 6000]
