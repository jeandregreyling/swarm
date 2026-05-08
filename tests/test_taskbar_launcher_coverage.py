import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'app.js'
TPL = ROOT / 'frontend' / 'templates' / 'terminal_base.html'


def test_taskbar_launcher_strip_exists_in_shell_template():
    tpl = TPL.read_text()
    assert 'id="taskbar-launchers"' in tpl


def test_taskbar_launchers_are_derived_from_quick_access_tiles():
    src = APP_JS.read_text()
    assert "function syncTaskbarLaunchers() {" in src
    assert "const PINNED_LAUNCHERS = ['chat', 'terminal', 'knowledge', 'studio', 'media-center', 'tasker'];" in src
    assert "'media-center': { title: 'Media Center', template: 'view-media-center' }" in src
    assert "'tasker':       { title: 'Tasker',       template: 'view-tasker' }" in src
    assert "document.querySelectorAll('#quick-cards .home-card[data-win-id]')" in src
    assert "if (!winId || !winTitle || winId === 'email') return;" in src
    assert "btn.innerHTML = fridaysWindowIconMarkup(winId);" in src
    assert "openWindow(winId, winTitle, String(node?.dataset?.winTemplate || `view-${winId}`));" in src


def test_media_center_tile_is_not_allowed_to_hide():
    src = (ROOT / 'frontend' / 'static' / 'js' / 'views' / 'diamond.js').read_text()
    assert "winId === 'localai' || winId === 'media-center'" in src
    assert "id !== 'localai' && id !== 'media-center'" in src


def test_taskbar_launcher_order_resyncs_after_tile_reorder():
    src = APP_JS.read_text()
    assert "syncTaskbarLaunchers();" in src
    assert "window.syncTaskbarLaunchers = syncTaskbarLaunchers;" in src


def test_every_quick_access_tile_has_an_explicit_shared_icon():
    tpl = TPL.read_text()
    src = APP_JS.read_text()
    wm = (ROOT / 'frontend' / 'static' / 'js' / 'core' / 'window-manager.js').read_text()
    tile_ids = set(re.findall(r'data-win-id="([^"]+)"', tpl))
    icon_ids = set(match.strip("'\"") for match in re.findall(r'^\s*([\'\"]?[-\w]+[\'\"]?)\s*:\s*\'<svg', wm, re.M))
    assert tile_ids <= icon_ids
