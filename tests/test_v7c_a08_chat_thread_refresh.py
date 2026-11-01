"""V7C-A08 — Main chat thread controls regression audit.

Project: P-E9BAE4159F
Step:    S-400E270715

User complaints:
  - "home screen still isn't refreshing" (transcript L13101)
  - "main chat still doesn't open with a new thread" (L13101)
  - "when refreshing the terminal it still doesn't start with a new thread" (L19822)

Contract: F5/reload ALWAYS starts on a fresh thread; stale active-thread key
is wiped before UI paints; bfcache restore also resets.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'chat.js'
HOME_CHAT_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'home-chat.js'


# R1 FUNCTIONAL — chat.js wipes stale thread marker on load
def test_r1_chat_js_wipes_stale_thread_on_load():
    src = CHAT_JS.read_text()
    assert "localStorage.removeItem('fridays-chat-active-thread')" in src
    assert "__fridaysChatForceNewThread = window.__fridaysChatForceNewThread ?? true" in src


# R2 FUNCTIONAL — home-chat restores its saved thread instead of wiping it
def test_r2_home_chat_restores_saved_thread_on_init():
    src = HOME_CHAT_JS.read_text()
    init_idx = src.find("window.initHomeChat = function")
    assert init_idx >= 0
    body = src[init_idx:src.find("// ── Session 28", init_idx)]
    assert "localStorage.getItem(HC_ACTIVE_THREAD_KEY)" in body
    assert "localStorage.removeItem(HC_ACTIVE_THREAD_KEY)" not in body
    assert "_hcClearMessages()" not in body
    assert "window.__fridaysChatConversationId = null" not in body


# R3 BFCACHE — back/forward restore keeps the visible thread and only refreshes history
def test_r3_bfcache_pageshow_keeps_thread():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("pageshow")
    assert idx >= 0
    block = src[idx:src.find("});", idx)]
    assert "ev.persisted" in block
    assert "_hcLoadThreadsListOnly()" in block
    assert "_hcConvId = null" not in block


# R4 CROSS-SURFACE — deletion of current conv falls back to new thread
def test_r4_delete_current_conv_falls_back():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("swarm:conversation-changed")
    assert idx >= 0
    end = src.find("document.addEventListener('visibilitychange'", idx)
    assert end > idx
    block = src[idx:end]
    assert "detail.type === 'deleted'" in block
    assert "_hcNewThread()" in block
    assert "_hcLoadThreadsListOnly()" in block
    assert "_hcLoadThreads();" not in block


# R5 THREAD LOAD — a deleted saved thread drops its stale marker
def test_r5_missing_saved_thread_starts_fresh():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("function _hcLoadMessages")
    assert idx >= 0
    block = src[idx:src.find("// ── Render bubbles", idx)]
    assert "r.status === 404" in block
    assert "_hcNewThread()" in block
    new_thread = src[src.find("function _hcNewThread"):]
    assert "localStorage.removeItem(HC_ACTIVE_THREAD_KEY)" in new_thread[:600]
    assert "window.__fridaysChatConversationId = null" not in block


# R6 EXPAND HANDOFF — Expand button preserves current thread to main chat
def test_r6_expand_preserves_thread():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("expandBtn")
    assert idx >= 0
    block = src[idx:idx + 800]
    assert "__fridaysChatOpenWithConvId = _hcConvId" in block


def test_home_chat_uses_separate_active_thread_key():
    src = HOME_CHAT_JS.read_text()
    assert "const HC_ACTIVE_THREAD_KEY = 'fridays-home-chat-active-thread'" in src
    assert "const HC_ACTIVE_THREAD_KEY = 'fridays-chat-active-thread'" not in src


def test_home_chat_does_not_own_main_chat_active_thread():
    src = HOME_CHAT_JS.read_text()
    assert "window.__fridaysChatOpenWithConvId = _hcConvId" in src
    assert "window.__fridaysChatConversationId =" not in src


def test_home_chat_fresh_canvas_defaults_to_seven_not_stale_global_agent():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("function _hcGetEnabledAgents()")
    assert idx >= 0
    block = src[idx:idx + 900]
    assert "if (!_hcConvId)" in block
    assert "return ['seven']" in block
    assert block.find("return ['seven']") < block.find("const global = localStorage.getItem(HC_GLOBAL_AGENTS_KEY)")


# R7 REGRESSION GUARD — the main chat window still starts fresh on load.
# The home chat tile intentionally restores its own saved thread (see R2).
def test_r7_main_chat_load_path_never_reads_active_thread_key():
    src = CHAT_JS.read_text()
    assert "localStorage.getItem('fridays-chat-active-thread')" not in src
