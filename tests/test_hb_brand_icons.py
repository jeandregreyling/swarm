"""Practice 25 (owner 14 Nov): HB's own icons instead of generic emoji, in the theme's highlight colour, drawn like core/icons.js.
A flower for credit, a hummingbird flying to a flower for asking Fred, a sleeping hummingbird for maintenance."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/views/hb-brand-icons.js'
BASE = ROOT / 'frontend/templates/terminal_base.html'
HARNESS = r"""
global.document = { getElementById: () => null, createElement: () => ({}), head: { appendChild() {} }, querySelectorAll: () => [] };
global.window = {}; global.setInterval = () => 0; global.setTimeout = () => 0;
eval(require('fs').readFileSync(process.argv[2], 'utf8'));
const I = window.HBIcons;
console.log(JSON.stringify({ icons: I.ICONS, markers: I.MARKERS, a: I.marker('🌺 HB gives APEX a flower'), b: I.marker('🛠️ Fred is taking over'), c: I.marker('Plain text'),
  parts: I.split('📋 New task ✔ done, ⏸ parked ✘ failed - ⚠️ check 🧪 bench'), plain: I.split('no markers here') }));
"""


def test_practice_25_file_parses_and_page_loads_it():
    assert JS.exists(), 'create frontend/static/js/views/hb-brand-icons.js'
    if shutil.which('node'):
        subprocess.run(['node', '--check', str(JS)], check=True, capture_output=True)
    assert '<script src="/static/js/views/hb-brand-icons.js?v={{ ASSET_VERSION }}"></script>' in BASE.read_text()


def test_practice_25_icons_follow_the_theme_and_hb_style(tmp_path):
    if not shutil.which('node') or not JS.exists():
        pytest.skip('node or the icon file is missing')
    h = tmp_path / 'h.js'
    h.write_text(HARNESS)
    out = json.loads(subprocess.run(['node', str(h), str(JS)], check=True, capture_output=True, text=True).stdout)
    assert {'flower', 'bird', 'visit', 'sleeping'} <= set(out['icons'])
    for svg in out['icons'].values():
        assert 'currentColor' in svg and not re.search(r'#[0-9a-fA-F]{3,6}', svg)       # colour comes from the theme
        assert 'stroke-width="1.3"' in svg and 'stroke-linecap="round"' in svg            # drawn like core/icons.js
    assert 'var(--accent' in JS.read_text() and 'prefers-reduced-motion' in JS.read_text()
    assert out['a'] == {'icon': 'flower', 'rest': ' HB gives APEX a flower'}
    assert out['b']['icon'] == 'visit' and out['b']['rest'] == ' Fred is taking over'       # the emoji's variation mark goes too
    assert out['c'] is None


def test_practice_30_svg_is_the_standard_for_every_hb_marker(tmp_path):
    """Owner 14 Nov: "your icons still aren't using SVG as standard" - every marker HB writes becomes an HB line icon in the theme colour,
    anywhere in HB's messages, the live activity, the clipboard and the Needs-you bar."""
    if not shutil.which('node') or not JS.exists():
        pytest.skip('node or the icon file is missing')
    h = tmp_path / 'h.js'
    h.write_text(HARNESS)
    out = json.loads(subprocess.run(['node', str(h), str(JS)], check=True, capture_output=True, text=True).stdout)
    for mark in ('📋', '✅', '✔', '✘', '⚠', '⏸', '▶', '🔎', '🧪', '🌱', '📝', '📜', '↺', '☰', '❓', '⬇', '⚙', '🌺', '🤔', '🛠'):
        assert mark in out['markers'] and out['markers'][mark] in out['icons'], mark
    for svg in out['icons'].values():
        assert 'currentColor' in svg and not re.search(r'#[0-9a-fA-F]{3,6}', svg) and 'stroke-width="1.3"' in svg
    icons = [p['icon'] for p in out['parts'] if isinstance(p, dict)]
    assert icons == ['clipboard', 'check', 'pause', 'cross', 'warn', 'flask']                 # every marker, not just the first
    assert ' New task ' in out['parts'] and out['plain'] == ['no markers here']
    text = JS.read_text()
    assert '#hb-activity' in text and '#hb-clipboard' in text and '.hb-needs-you' in text


UI = ['frontend/static/js/hb-maintenance.js', 'frontend/static/js/views/hb-needs-you.js', 'frontend/static/js/views/hb-queue.js',
      'frontend/static/js/views/hb-approval-popup.js', 'frontend/static/js/views/hb-activity.js']
GLYPH = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u25A0-\u25FF\u2190-\u2196\u2198-\u21FF\u2300-\u23FF]')


def test_practice_31_no_hard_coded_icons_or_colours_in_hbs_interface(tmp_path):
    """Owner 14 Nov: "I still see the old maintenance icon when it just starts loading, that must be hard coded - what is our global rule on
    hard coding things?" Icons come only from HBIcons (by name); colours from the theme."""
    for rel in UI:
        text = (ROOT / rel).read_text()
        assert not GLYPH.findall(text), (rel, GLYPH.findall(text))
    assert "svg('sleeping')" in (ROOT / UI[0]).read_text()
    for rel in UI[3:]:
        assert not re.findall(r'(?<!,)#[0-9a-fA-F]{6}\b', (ROOT / rel).read_text()), rel     # only theme fallbacks inside var(--x, #...)
    if not shutil.which('node'):
        pytest.skip('node is missing')
    h = tmp_path / 'h.js'
    h.write_text(HARNESS.replace("console.log(JSON.stringify({ icons", "console.log(JSON.stringify({ svgflag: I.svg('flag'), icons"))
    out = json.loads(subprocess.run(['node', str(h), str(JS)], check=True, capture_output=True, text=True).stdout)
    assert out['svgflag'].startswith('<span class="hb-ico" data-hb-icon="flag"') and 'currentColor' in out['svgflag']
