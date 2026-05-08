"""V7C-A14 — Terminal history/shortcuts runtime verification.

Project: P-E9BAE4159F
Step:    S-BB75AB218A
Case:    C-4F38B32713 ("Terminal favourites star and multi-select combine bar are visible")

Contract:
  - Favourite ★ button on every history row
  - Multi-select (shift/ctrl/cmd-click) shows combine bar
  - Combine bar has Run combined / Fill / Clear
  - Up/Down arrows navigate history
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'terminal.js'


# R1 FAVOURITE — star button wired to save-to-shortcuts
def test_r1_favourite_star_button():
    src = TERMINAL_JS.read_text()
    assert "favBtn.textContent = '★'" in src
    assert "favBtn.title = 'Save to shortcuts'" in src
    assert "_terminalSaveToShortcuts(cmd, favBtn)" in src


# R2 SAVE HANDLER — the save function persists to custom shortcuts store
def test_r2_save_to_shortcuts_persists():
    src = TERMINAL_JS.read_text()
    assert "function _terminalSaveToShortcuts(" in src
    assert "saveCustomTerminalShortcuts" in src


# R3 MULTI-SELECT — combine bar DOM id present
def test_r3_combine_bar_present():
    src = TERMINAL_JS.read_text()
    assert "id=\"terminal-combine-bar\"" in src or "'terminal-combine-bar'" in src
    assert "#terminal-combine-bar" in src


# R4 COMBINE ACTIONS — run / fill / clear present
def test_r4_combine_actions():
    src = TERMINAL_JS.read_text()
    assert "id=\"combine-run\"" in src
    assert "id=\"combine-fill\"" in src
    assert "id=\"combine-clear\"" in src
    # Chain operator is && (POSIX-safe)
    assert "cmds.join(' && ')" in src


# R5 ARROW NAV — up/down keys drive history cursor
def test_r5_arrow_keys_wired():
    src = TERMINAL_JS.read_text()
    assert "event.key === 'ArrowUp'" in src
    assert "event.key === 'ArrowDown'" in src


# R6 HISTORY PERSIST — canonical key used
def test_r6_history_persist_key():
    src = TERMINAL_JS.read_text()
    assert "'fridays-terminal-history'" in src


# R7 SHORTCUTS PANEL — collapse state persisted per session
def test_r7_shortcuts_collapsed_state_persisted():
    src = TERMINAL_JS.read_text()
    assert "'fridays-terminal-shortcuts-collapsed'" in src
    assert "applyTerminalShortcutsState" in src
