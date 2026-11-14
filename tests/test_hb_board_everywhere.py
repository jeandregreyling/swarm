"""Practice 82 (owner 15 Nov): "I don't see a task board at all" - the board was only in the Home chat panel and hid itself
silently in a window that is not signed in as the owner."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/views/hb-queue.js'


def test_practice_82_board_is_placed_in_both_chat_windows():
    js = JS.read_text()
    assert "['hb-clipboard', 'home-chat-messages'], ['hb-clipboard-chat', 'chat-messages']" in js
    assert 'const all = holders(), el = all[0];' in js and 'all.slice(1).forEach(other =>' in js
    base = (ROOT / 'frontend/templates/terminal_base.html').read_text()
    assert 'id="home-chat-messages"' in base and 'id="chat-messages"' in base      # both anchors really exist on the page


def test_practice_82_chat_window_board_carries_the_switches():
    js = JS.read_text()
    assert "swHtml + '</div>'" in js and "const sw = e.target.closest('[data-switch]');" in js


def test_practice_82_a_window_that_is_not_the_owner_says_so():
    js = JS.read_text()
    assert 'if (r.status === 401 || r.status === 403) { notOwner(); return; }' in js
    assert 'it is not signed in as the owner' in js and 'href="/login"' in js


def test_practice_82_script_parses():
    done = subprocess.run(['node', '--check', str(JS)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-400:]
