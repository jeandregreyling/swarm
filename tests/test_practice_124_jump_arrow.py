"""Practice 124 (owner 17 Nov 2026): "The auto scroll and lock or not arrow at the bottom right of the chat screen went missing". Main chat's
arrow (#hc-jump-bottom) showed only while scrolled up or with auto scroll on, so once auto scroll was double-clicked off it vanished at the
bottom and could not be turned back on. It always shows now; faint when idle."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_practice_124_the_arrow_is_never_hidden():
    js = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    i = js.index('function _hcInitJumpButton()')
    block = js[i:i + 3000]
    assert "btn.classList.toggle('show', true);" in block and "btn.classList.toggle('idle', !(away || auto));" in block
    assert "btn.classList.toggle('show', away || auto);" not in block
    css = (ROOT / 'frontend/static/css/home-chat.css').read_text()
    assert '#hc-jump-bottom.show.idle { opacity: .4; }' in css


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
def test_practice_124_home_chat_still_parses():
    assert subprocess.run(['node', '--check', str(ROOT / 'frontend/static/js/views/home-chat.js')], capture_output=True).returncode == 0
