from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "frontend" / "templates" / "terminal_base.html"
TASKBAR_CSS = ROOT / "frontend" / "static" / "css" / "taskbar.css"
THEME_JS = ROOT / "frontend" / "static" / "js" / "core" / "theme.js"
APP_JS = ROOT / "frontend" / "static" / "js" / "core" / "app.js"
ACCESS_JS = ROOT / "frontend" / "static" / "js" / "views" / "access.js"
LOCALAI_JS = ROOT / "frontend" / "static" / "js" / "views" / "localai.js"
LOCALAI_CSS = ROOT / "frontend" / "static" / "css" / "views" / "localai.css"
POTATO_JS = ROOT / "frontend" / "static" / "js" / "views" / "potato-farm.js"


def test_mail_and_theme_taskbar_controls_share_shell_class():
    tpl = TEMPLATE.read_text()
    assert 'id="email-dot-btn" class="taskbar-control-btn"' in tpl
    assert 'id="theme-picker-btn" class="taskbar-control-btn"' in tpl

    for control_id in ("email-dot-btn", "theme-picker-btn"):
        idx = tpl.index(f'id="{control_id}"')
        tag_start = tpl.rfind("<button", 0, idx)
        tag_end = tpl.index(">", idx)
        tag = tpl[tag_start:tag_end]
        assert "style=" not in tag, f"{control_id} must not use one-off inline styles"


def test_theme_picker_is_not_clipped_by_taskbar():
    css = TASKBAR_CSS.read_text()
    assert "overflow-y: visible;" in css
    assert "#theme-picker-menu" in css
    assert "position: fixed;" in css
    assert "#theme-picker-wrap.open #theme-picker-menu" in css


def test_theme_picker_button_has_bound_click_handler():
    tpl = TEMPLATE.read_text()
    js = THEME_JS.read_text()
    assert 'theme.js?v={{ ASSET_VERSION }}' in tpl
    idx = tpl.index('id="theme-picker-btn"')
    tag_start = tpl.rfind("<button", 0, idx)
    tag_end = tpl.index(">", idx)
    assert "onclick=" not in tpl[tag_start:tag_end]
    assert "function _initTaskbarThemePicker()" in js
    assert "btn.addEventListener('pointerdown'" in js
    assert "btn.addEventListener('click'" in js
    assert "e.__fridaysThemeHandled" in js
    assert "function _positionThemePickerMenu()" in js
    assert "setAttribute('aria-expanded'" in js


def test_bottom_taskbar_buttons_toggle_existing_windows():
    tpl = TEMPLATE.read_text()
    src = APP_JS.read_text()
    assert 'app.js?v={{ ASSET_VERSION }}-taskbar2' in tpl
    assert "function toggleTaskbarWindow(id, title, templateId)" in src
    assert "winManager.minimize(windowKey);" in src
    assert "toggleTaskbarWindow('email','Email','view-email')" in tpl
    assert "toggleTaskbarWindow(winId, winTitle" in src


def test_agents_chat_action_only_selects_chat_agent_toggle():
    access = ACCESS_JS.read_text()
    localai = LOCALAI_JS.read_text()
    tpl = TEMPLATE.read_text()
    assert 'access.js?v={{ ASSET_VERSION }}-agent-chat1' in tpl
    assert 'localai.js?v={{ ASSET_VERSION }}-seven-first1' in tpl
    assert "function agentsSelectChatAgent(name)" in access
    assert "window.agentsSelectChatAgent = agentsSelectChatAgent;" in access
    assert "is not enabled in Chat" in access
    assert "document.querySelectorAll('.agent-toggle-btn, [data-agent]')" not in access
    assert "document.querySelectorAll('.agent-toggle-btn, [data-agent]')" not in localai
    assert ".chat-agent-toggle" in access


def test_localai_exposes_seven_runtime_controls():
    tpl = TEMPLATE.read_text()
    localai = LOCALAI_JS.read_text()
    css = LOCALAI_CSS.read_text()
    assert "Seven Runtime" in tpl
    assert "Seven Runtime first" in tpl
    assert "Fallback model store" in tpl
    assert "seven-runtime-status-badge" in tpl
    assert "seven-runtime-quick-prompt" in tpl
    assert "/api/localai/seven-runtime/status" in localai
    assert "/api/localai/seven-runtime/start" in localai
    assert "/api/localai/seven-runtime/stop" in localai
    assert "/api/localai/seven-runtime/chat" in localai
    assert "timeout_seconds: 90" in localai
    assert "function _renderSevenRuntime" in localai
    assert "function localaiSevenRuntimeChat" in localai
    assert ".localai-panel-seven" in css and "order: -1" in css


def test_potato_proof_is_not_a_permanent_global_banner():
    tpl = TEMPLATE.read_text()
    js = POTATO_JS.read_text()
    assert "id=\"potato-global-proof\"" not in tpl
    assert "potato-global-proof" not in js
    assert 'potato-farm.js?v={{ ASSET_VERSION }}' in tpl
    assert "function _pfIsNodeFresh" in js
    assert "offline/stale" in js
