"""V7C-R4 — Chat surface regression sweep.

Project: P-E9BAE4159F
Step:    S-29B2C35DA4

User complaints (transcript 2026-04-23 line 16851):
  - "it now insists on tagging gemma automatically"
  - "deselects the models I selected before typing"
  - "By default model selection should be manual"

Fixes previously landed but untested:
  1. Default __fridaysChatRelayAuto is FALSE (manual-first).
  2. _applyClassifyAgents early-returns when relay-auto is off.
  3. Manual selections preserved when classifier runs.

This test locks all three invariants.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'chat.js'


def _body(src: str, fn_name: str) -> str:
    """Extract a function body by brace-counting from `function <name>`."""
    anchor = f'function {fn_name}('
    i = src.find(anchor)
    assert i >= 0, f"function {fn_name} not found"
    j = src.find('{', i)
    depth = 0
    while j < len(src):
        c = src[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    raise AssertionError(f"unterminated body for {fn_name}")


# Reviewer 1: FUNCTIONAL — manual-first default
def test_r1_relay_auto_defaults_off():
    src = CHAT_JS.read_text()
    assert "localStorage.getItem(CHAT_RELAY_AUTO_KEY) === '1'" in src, (
        "Default must be strict-equals '1' (opt-in). Any other pattern "
        "(e.g. !== '0') would make auto-on the default and re-break the "
        "'Gemma keeps getting selected' bug."
    )


# Reviewer 2: REGRESSION — no opt-out default patterns reintroduced
def test_r2_no_opt_out_default():
    src = CHAT_JS.read_text()
    forbidden = [
        "localStorage.getItem(CHAT_RELAY_AUTO_KEY) !== '0'",
        "localStorage.getItem(CHAT_RELAY_AUTO_KEY) != '0'",
    ]
    for f in forbidden:
        assert f not in src, f"Opt-out default reintroduced: {f}"


# Reviewer 3: CLASSIFIER — bails when auto is off
def test_r3_classifier_respects_manual_mode():
    src = CHAT_JS.read_text()
    body = _body(src, '_applyClassifyAgents')
    assert "if (!window.__fridaysChatRelayAuto) return;" in body, (
        "_applyClassifyAgents must early-return when auto is off, otherwise "
        "it rewrites the agent selection on every keystroke."
    )


# Reviewer 4: MANUAL PRESERVATION — manual marks survive classifier
def test_r4_manual_selection_preserved():
    src = CHAT_JS.read_text()
    body = _body(src, '_applyClassifyAgents')
    # Manual keys must be collected before any overwrite.
    assert "manualKeys" in body
    assert "'manual'" in body
    # Overwrite loop must guard on manualKeys.has.
    assert "if (!manualKeys.has(k))" in body


# Reviewer 5: UI HANDLER — manual toggle flags override
def test_r5_manual_toggle_sets_override_flag():
    src = CHAT_JS.read_text()
    body = _body(src, '_onManualAgentToggle')
    assert "__classifyManualOverride = true" in body


# Reviewer 6: CHECKBOX WIRING — onchange tags selection state
def test_r6_checkbox_marks_manual_on_toggle():
    src = CHAT_JS.read_text()
    # The inline handler in renderChatAgentToggles must set manual state on check.
    assert "_setAgentSelectionState('${agent.value}',this.checked?'manual':null)" in src, (
        "Agent checkbox must tag state='manual' when checked so the classifier "
        "does not silently remove it."
    )


# Reviewer 7: PERSISTENCE — relay-auto toggle persists to storage
def test_r7_relay_auto_toggle_persists():
    src = CHAT_JS.read_text()
    body = _body(src, 'onChatRelayAutoToggle')
    assert "localStorage.setItem(CHAT_RELAY_AUTO_KEY" in body
