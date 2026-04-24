import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / 'frontend' / 'templates' / 'terminal_base.html'


def test_monitor_and_studio_scripts_have_cache_bust_tokens():
    tpl = TPL.read_text()
    assert re.search(r'/static/js/views/monitor\.js\?v=\d+', tpl)
    assert re.search(r'/static/js/views/studio\.js\?v=\d+', tpl)


def test_settings_bridge_core_scripts_have_cache_bust_tokens():
    tpl = TPL.read_text()
    assert re.search(r'/static/js/core/window-manager\.js\?v=\d+', tpl)
    assert re.search(r'/static/js/core/theme\.js\?v=\d+', tpl)
    assert re.search(r'/static/js/core/app\.js\?v=\d+', tpl)
    assert re.search(r'/static/js/core/init\.js\?v=\d+', tpl)


def test_taskbar_stylesheet_has_cache_bust_token():
    tpl = TPL.read_text()
    assert re.search(r'/static/css/taskbar\.css\?v=\d+', tpl)
