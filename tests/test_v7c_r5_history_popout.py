"""V7C-R5 — History and popout behaviour.

Project: P-E9BAE4159F
Step:    S-2D896B568F
Case:    C-45501068B3 ("Terminal history opens as floating draggable window")

Contract: Terminal history opens as a fixed-position floating window with
drag, close button, Esc-close, and clean restore on close.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'terminal.js'


def _body(src: str, fn_name: str) -> str:
    anchor = f'function {fn_name}('
    i = src.find(anchor)
    assert i >= 0, f"function {fn_name} not found"
    j = src.find('{', i)
    depth = 0
    while j < len(src):
        if src[j] == '{': depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0: return src[i:j + 1]
        j += 1
    raise AssertionError(f"unterminated {fn_name}")


# R1 FUNCTIONAL — promote/demote functions exist
def test_r1_promote_demote_defined():
    src = TERMINAL_JS.read_text()
    assert "function _terminalPromoteHistoryPanel(" in src
    assert "function _terminalDemoteHistoryPanel(" in src


# R2 WINDOW CHROME — fixed + draggable header
def test_r2_floating_window_chrome():
    body = _body(TERMINAL_JS.read_text(), '_terminalPromoteHistoryPanel')
    assert "position:fixed" in body
    assert "cursor:move" in body  # header is draggable
    assert "terminal-history-floating" in body


# R3 DRAG WIRING — mousedown/mousemove/mouseup bound
def test_r3_drag_handlers_bound():
    body = _body(TERMINAL_JS.read_text(), '_terminalPromoteHistoryPanel')
    assert "mousedown" in body
    assert "addEventListener('mousemove', onMove)" in body
    assert "addEventListener('mouseup', onUp)" in body


# R4 CLOSE AFFORDANCES — Esc + × button both close
def test_r4_close_affordances():
    body = _body(TERMINAL_JS.read_text(), '_terminalPromoteHistoryPanel')
    assert "Close history window" in body  # aria-label on × btn
    assert "e.key === 'Escape'" in body


# R5 CLEANUP — demote restores parent + removes wrap + unbinds listeners
def test_r5_demote_cleans_up():
    body = _body(TERMINAL_JS.read_text(), '_terminalDemoteHistoryPanel')
    assert "_origParent" in body
    assert "wrap.remove()" in body
    assert "_cleanup" in body
    assert "removeEventListener('keydown'" in body


# R6 SYNC — sync UI routes open-state through promote/demote
def test_r6_sync_routes_through_promote():
    body = _body(TERMINAL_JS.read_text(), '_terminalSyncHistoryUi')
    assert "_terminalPromoteHistoryPanel" in body
    assert "_terminalDemoteHistoryPanel" in body


# R7 PERSISTENCE — history survives in localStorage under the canonical key
def test_r7_history_persisted():
    src = TERMINAL_JS.read_text()
    assert "localStorage.setItem('fridays-terminal-history'" in src
    assert "localStorage.getItem('fridays-terminal-history'" in src
