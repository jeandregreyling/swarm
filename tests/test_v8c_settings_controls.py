"""V8C — Settings panel controls regression guard.

Locks in the decision made in Session 24:
  • Atmosphere engine controls (atmosphere/accent/hue/contrast/opacity/glow)
    must be `<input type="range">` sliders with `oninput` live-preview.
  • Font-size must stay a `<select>` dropdown for precision (user preference).
  • Font-family stays a `<select>`.
  • Every slider must have a matching JS handler and the handler must clamp.

Also runs a 7-reviewer council pass on the same surface so the fix can't
silently regress again. Each reviewer asserts its own invariant.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "frontend" / "templates" / "terminal_base.html"
THEME_JS = ROOT / "frontend" / "static" / "js" / "core" / "theme.js"
CSS = ROOT / "frontend" / "static" / "css" / "modals.css"

SLIDER_IDS = (
    "atmosphere-slider",
    "accent-slider",
    "hue-slider",
    "contrast-slider",
    "opacity-slider",
    "glow-slider",
)

SLIDER_HANDLERS = {
    "atmosphere-slider": "onAtmosphereSliderInput",
    "accent-slider":     "onAccentSliderInput",
    "hue-slider":        "onHueSliderInput",
    "contrast-slider":   "onContrastSliderInput",
    "opacity-slider":    "onOpacitySliderInput",
    "glow-slider":       "onGlowSliderInput",
}


# ── Reviewer #1 — Functional: sliders are <input type=range> ────────────────
def test_reviewer1_sliders_are_range_inputs():
    html = TEMPLATE.read_text()
    for sid in SLIDER_IDS:
        m = re.search(r'<(input|select)[^>]*id="' + sid + r'"[^>]*>', html)
        assert m, f"{sid}: element not found"
        tag = m.group(1)
        assert tag == "input", f"{sid}: expected <input>, got <{tag}>"
        assert 'type="range"' in m.group(0), f"{sid}: missing type=range"


# ── Reviewer #2 — UX: font-size stays precise (dropdown) ────────────────────
def test_reviewer2_font_size_is_select():
    html = TEMPLATE.read_text()
    m = re.search(r'<(input|select)[^>]*id="theme-font-size-select"', html)
    assert m, "theme-font-size-select missing"
    assert m.group(1) == "select", (
        "font-size must stay <select> for precision — user preference"
    )


# ── Reviewer #3 — Interactivity: oninput wiring (not onchange only) ─────────
def test_reviewer3_sliders_have_oninput():
    html = TEMPLATE.read_text()
    for sid, handler in SLIDER_HANDLERS.items():
        m = re.search(r'<input[^>]*id="' + sid + r'"[^>]*>', html)
        assert m, f"{sid}: element not found"
        el = m.group(0)
        assert "oninput=" in el, (
            f"{sid}: sliders need oninput= for live preview, not only onchange"
        )
        assert handler in el, f"{sid}: handler {handler}() not wired"


# ── Reviewer #4 — JS: every handler exists and clamps ───────────────────────
def test_reviewer4_handlers_exist_and_clamp():
    js = THEME_JS.read_text()
    for sid, handler in SLIDER_HANDLERS.items():
        assert re.search(r"function\s+" + handler + r"\s*\(", js), (
            f"{handler}() missing in theme.js"
        )
    # Spot-check clamps — every accent/hue/contrast/glow should go through
    # _clampAtmosphereValue, and opacity through _clampTransparencyValue.
    for h in ("onAccentSliderInput", "onHueSliderInput",
              "onContrastSliderInput", "onGlowSliderInput",
              "onAtmosphereSliderInput"):
        body = _handler_body(js, h)
        assert "_clampAtmosphereValue" in body, f"{h} missing clamp"
    op = _handler_body(js, "onOpacitySliderInput")
    assert "_clampTransparencyValue" in op, "opacity handler missing clamp"


# ── Reviewer #5 — Accessibility: focus ring + hit target in CSS ─────────────
def test_reviewer5_css_accessibility():
    css = CSS.read_text()
    block = css.split("V8C — ELEGANT ATMOSPHERE SLIDERS", 1)
    assert len(block) == 2, "V8C slider CSS block missing"
    slider_css = block[1]
    assert "focus-visible" in slider_css, "no :focus-visible state"
    assert "height: 26px" in slider_css, "hit target too small"
    assert "accent-color: var(--accent)" in slider_css, "native fill not wired"


# ── Reviewer #6 — Visual: progress fill + thumb + chevron ───────────────────
def test_reviewer6_visual_polish():
    css = CSS.read_text()
    # Firefox progress fill (Chrome uses accent-color).
    assert "::-moz-range-progress" in css, "no progress fill for Firefox"
    # Thumb has a gradient not just a flat colour.
    assert "radial-gradient" in css, "thumb missing polish"
    # Select has a chevron (rendered via linear-gradient trick).
    assert "#settings-box select" in css, "select not styled"
    assert "linear-gradient(45deg" in css, "select chevron missing"


# ── Reviewer #7 — Reset: DOM reflects the reset, not only localStorage ──────
def test_reviewer7_reset_syncs_dom():
    chat_js = (ROOT / "frontend" / "static" / "js" / "views" / "chat.js").read_text()
    # resetThemeAndFontDefaults() must snap the opacity control AND its readout.
    fn = _handler_body(chat_js, "resetThemeAndFontDefaults")
    assert "opacity-slider" in fn, "reset doesn't touch opacity-slider"
    assert "opacity-value" in fn, "reset doesn't update opacity readout"
    assert "setChatUiScale" in fn, "reset doesn't re-apply default font scale"


# ── Helpers ─────────────────────────────────────────────────────────────────
def _handler_body(js: str, name: str) -> str:
    """Return the body of function `name` in a JS source string."""
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", js)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(js) and depth:
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
        i += 1
    return js[start:i]
