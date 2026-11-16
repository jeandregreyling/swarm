"""Practice 54 (15 Nov): hb_change_sets.py has each helper once (practice 52 was applied twice by the tool it was fixing)."""
from pathlib import Path


def test_practice_54_change_set_tool_has_no_doubled_lines():
    src = (Path(__file__).resolve().parents[1] / 'core/hb_change_sets.py').read_text()
    assert src.count('def _edit_in(text, edit):') == 1 and src.count('if _edit_in(before, edit):') == 1
