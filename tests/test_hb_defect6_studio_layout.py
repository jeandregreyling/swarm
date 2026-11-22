"""Tests for Defect 6: Studio layout overhaul — Plan Steps FIRST at top with step codes, Blackboard collapsed below."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_studio_renders_plan_steps_before_collapsed_blackboard_drawer():
    js_path = ROOT / 'frontend/static/js/views/projects.js'
    js = js_path.read_text(encoding='utf-8')
    steps_pos = js.find('id="studio-plan-steps-top"')
    bb_pos = js.find('<details id="studio-blackboard-drawer"')
    assert steps_pos > 0 and bb_pos > steps_pos
    assert 'fuckitforlater' in js
    assert 'id="pd-hide-done"' in js
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
