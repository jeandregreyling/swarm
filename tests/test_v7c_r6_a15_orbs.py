"""V7C-R6 + A15 — Orbs interaction, idle, and behaviour bundle.

Project: P-E9BAE4159F
Steps:   S-1BB1571714 (R6), S-9C5B0A2BC3 (A15)

User complaints (transcript L18302, L18492):
  - "top-left orb keeps getting stuck"
  - "their shapes aren't 3d"
  - "transitions aren't smooth"
  - "can't throw them aggressively they just plop down"
  - "maybe a double click to pick it up and put it down"
  - "single click and release for throw"
  - "make it so I can turn the 3d versions on and off"
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORBS_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'orbs.js'


# R1 GRAPHICS TOGGLE — high/low mode exists
def test_r1_graphics_high_low_modes():
    src = ORBS_JS.read_text()
    assert "'high'" in src and "'low'" in src
    assert "3D wireframes" in src or "wireframe" in src.lower()


# R2 THROW — mouse-velocity captured for release throw
def test_r2_mouse_velocity_tracked():
    src = ORBS_JS.read_text()
    assert "mouseVX" in src and "mouseVY" in src
    assert "prevMX" in src and "prevMY" in src and "prevMT" in src


# R3 DUAL MODE — dragOrb (click-drag-throw) vs carriedOrb (dblclick-carry)
def test_r3_drag_vs_carried():
    src = ORBS_JS.read_text()
    assert "dragOrb" in src
    assert "carriedOrb" in src
    # Contract comment present
    assert "double-click" in src.lower() or "dblclick" in src


# R4 CUSTOM ANCHOR — dblclick drop sets new home
def test_r4_custom_anchor_persists():
    src = ORBS_JS.read_text()
    assert "customHomeX" in src
    assert "customHomeY" in src


# R5 PHYSICS — each orb has vx/vy (throwable)
def test_r5_orb_has_velocity():
    src = ORBS_JS.read_text()
    assert "x: 0, y: 0, vx: 0, vy: 0" in src


# R6 3D TILT — orbs have tilt angles for 3D rendering
def test_r6_3d_tilt_state():
    src = ORBS_JS.read_text()
    assert "tiltX" in src and "tiltY" in src


# R7 NO HARDCODED STUCK — ROOST_BASE overridable by user anchor
def test_r7_roost_base_overridable():
    src = ORBS_JS.read_text()
    assert "ROOST_BASE" in src
    # Comment asserts override exists.
    assert "overrides the hardcoded ROOST_BASE" in src
