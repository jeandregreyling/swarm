"""V7C-R9 + A11 — Agents tab layout and role contract.

Project: P-E9BAE4159F
Steps:   S-C0BB028EC3 (R9), S-EDC56EB0EF (A11)

Locks:
  - #agent-number is a <select> (dropdown), not a number spinner
  - Dropdown renders all 0..22 slots with occupant/taken/empty markers
  - Slot role is a hardcoded READ-ONLY readout keyed by slot number
  - Description is a separate editable <input>
  - Responsive layout uses grid with 2 columns (collapses naturally on narrow)
  - Side list / detail preserves layout via grid, not absolute positioning
"""
from pathlib import Path

ACCESS = (Path(__file__).resolve().parents[1] / 'frontend' / 'static' / 'js' / 'views' / 'access.js').read_text()


def test_r9_r1_slot_dropdown_not_spinner():
    assert 'id="agent-number"' in ACCESS
    # Dropdown container — not <input type=number>.
    assert '<select id="agent-number"' in ACCESS
    assert 'type="number"' not in ACCESS.split('id="agent-number"')[0][-400:]


def test_r9_r2_slot_range_0_to_22():
    # All 0..22 slots enumerated with occupant status.
    assert 'for (let n = 0; n <= 22; n++)' in ACCESS
    assert '(current)' in ACCESS
    assert '(taken)' in ACCESS
    assert '(empty)' in ACCESS.replace('— empty', '(empty)') or '— empty' in ACCESS


def test_r9_r3_slot_role_hardcoded_readonly():
    # Hardcoded map and a "not editable" affordance label.
    assert 'const SLOT_ROLES' in ACCESS
    assert 'hardcoded by slot number, not editable' in ACCESS
    assert 'id="agent-slot-role-readout"' in ACCESS


def test_r9_r4_description_editable_input():
    # Description is a separate input element (editable), distinct from slot role.
    assert 'id="agent-role"' in ACCESS
    assert 'editable, shown in lists and tooltips' in ACCESS


def test_r9_r5_responsive_grid_layout():
    # Two-column grid, natural collapse via grid-template-columns.
    assert 'grid-template-columns:1fr 1fr' in ACCESS


def test_r9_a11_slot_saved_with_number():
    assert "Number(document.getElementById('agent-number')?.value" in ACCESS


def test_r9_r7_taken_slot_disabled():
    # Taken-by-someone-else slots are disabled so user cannot collide.
    assert 'taken ? \'disabled\' : \'\'' in ACCESS
