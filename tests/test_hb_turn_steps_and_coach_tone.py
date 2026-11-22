"""Top-of-bubble persistent Thinking panel (hb-turn-steps.js) and polite HB coaching tone."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_turn_steps_prepends_liquid_glass_thinking_panel_above_reply():
    js = (ROOT / 'frontend/static/js/hb-turn-steps.js').read_text(encoding='utf-8')
    assert '💭 Thinking · How APEX got here' in js
    assert 'host.prepend' in js
    assert 'backdrop-filter:blur(10px)' in js


def test_hb_step_check_uses_polite_coaching_wording():
    src = (ROOT / 'core/apex_tools.py').read_text(encoding='utf-8')
    assert 'quick tip: read it with alm_step_get first' in src
    assert 'this answer is not based on it' not in src
