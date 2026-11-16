"""Practice 112 (owner 16 Nov 2026): "the old icons still show before the SVG style is applied" - HB's emoji markers were swapped for SVG
icons only on a 1.5-second timer, so every new message showed its emoji first. New content is now decorated before the browser paints it."""
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / 'frontend/static/js/views/hb-brand-icons.js'


def test_practice_112_decorates_before_paint():
    src = JS.read_text()
    assert 'new MutationObserver(soon)' in src and 'queueMicrotask(' in src
    assert "childList: true, subtree: true, characterData: true" in src and 'attributes: true' not in src
    assert 'setInterval(() => decorate(document), 1500)' not in src


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
def test_practice_112_still_parses():
    assert subprocess.run(['node', '--check', str(JS)], capture_output=True, text=True).returncode == 0
