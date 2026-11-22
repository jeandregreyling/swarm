"""Practice 226: One-window main chat (A-F).

Chunk A: one column - Live pane on top showing only workers with an active run,
chat log below, drag divider (frontend/static/js/hb-live.js).
"""
import re
from pathlib import Path

JS = Path("frontend/static/js/hb-live.js")


def _src() -> str:
    return JS.read_text(encoding="utf-8")


def test_a_drag_divider_exists():
    """A drag divider element is created between the Live pane and the chat log."""
    src = _src()
    # There must be a divider element with id or class containing 'divider'
    assert re.search(r"hb-live-divider", src), "No drag divider element found in hb-live.js"


def test_a_divider_is_draggable():
    """The divider has a mousedown/touchstart handler for dragging."""
    src = _src()
    assert re.search(r"(mousedown|touchstart)", src), "No drag handler (mousedown/touchstart) found"


def test_a_active_workers_only():
    """The Live pane renders only workers with an active run, not all lanes."""
    src = _src()
    # The render call for the pane must filter to active/busy workers only.
    # Look for a filter or parameter that restricts to active runs.
    assert re.search(r"(activeOnly|active_only|onlyActive|only_active|activeWorkers|active_workers)", src), \
        "No active-only filter found in hb-live.js"


def test_a_one_column_layout():
    """The layout is a single column: Live pane on top, chat below, no side-by-side."""
    src = _src()
    # The pane is inserted before/above the chat messages (not beside them).
    # Check that the pane is a block element in the main column flow.
    assert re.search(r"(display:\s*flex|flex-direction:\s*column)", src), \
        "No flex column layout found for the one-column arrangement"
