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


# R2 FUNCTIONAL — home-chat resets conv id before paint
def test_r2_home_chat_resets_conv_before_paint():
    src = HOME_CHAT_JS.read_text()
    # initHomeChat must null the convId before _hcClearMessages/_hcShowWelcome.
    init_idx = src.find("window.initHomeChat = function")
    assert init_idx >= 0
    # Carve out just the init body to reason about it.
    body = src[init_idx:init_idx + 2000]
    for needle in [
        "localStorage.removeItem(HC_ACTIVE_THREAD_KEY)",
        "_hcConvId = null",
        "window.__fridaysChatConversationId = null",
        "_hcClearMessages()",
        "_hcShowWelcome(true)",
    ]:
        assert needle in body, f"init must call {needle}"


# R3 BFCACHE — back/forward restore also resets
def test_r3_bfcache_pageshow_resets():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("pageshow")
    assert idx >= 0
    block = src[idx:idx + 800]
    assert "ev.persisted" in block
    assert "_hcConvId = null" in block
    assert "_hcShowWelcome(true)" in block


# R4 CROSS-SURFACE — deletion of current conv falls back to new thread
def test_r4_delete_current_conv_falls_back():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("swarm:conversation-changed")
    assert idx >= 0
    block = src[idx:idx + 400]
    assert "detail.type === 'deleted'" in block
    assert "_hcNewThread()" in block


# R5 THREAD LOAD — load also wipes stale marker
def test_r5_thread_load_wipes_stale_marker():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("function _hcLoadThreads")
    assert idx >= 0
    block = src[idx:idx + 800]
    assert "localStorage.removeItem(HC_ACTIVE_THREAD_KEY)" in block
    assert "window.__fridaysChatConversationId = null" in block


# R6 EXPAND HANDOFF — Expand button preserves current thread to main chat
def test_r6_expand_preserves_thread():
    src = HOME_CHAT_JS.read_text()
    idx = src.find("expandBtn")
    assert idx >= 0
    block = src[idx:idx + 800]
    assert "__fridaysChatOpenWithConvId = _hcConvId" in block


# R7 REGRESSION GUARD — load path must wipe, not read, the active thread key
def test_r7_load_path_never_reads_active_thread_key():
    """The key may legitimately be written during a session (so floating chat
    can latch onto the active thread), but on LOAD it must only ever be
    removed — never read to hydrate state. Any `getItem(active-thread)` at
    module scope or in init flows would re-introduce the 'refresh restores
    old thread' bug."""
    for p in (CHAT_JS, HOME_CHAT_JS):
        src = p.read_text()
        for forbidden in [
            "localStorage.getItem('fridays-chat-active-thread')",
            "localStorage.getItem(HC_ACTIVE_THREAD_KEY)",
        ]:
            assert forbidden not in src, (
                f"{p.name} reads the active-thread key ({forbidden}). "
                "On reload this would restore the old thread — A08 violation."
            )
