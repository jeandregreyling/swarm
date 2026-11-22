"""Tests for Defect 4: Left Sundial stable hover/click-to-pin tooltips & unclipped Core Workspace hover glow."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_left_sundial_stable_pin_tooltips_and_unclipped_workspace_glow():
    js_path = ROOT / 'frontend/static/js/views/diamond.js'
    js = js_path.read_text(encoding='utf-8')
    assert 'tip._pinned' in js and '650' in js
    assert "e.key === 'Escape'" in js
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr

    css = (ROOT / 'frontend/static/css/home-chat.css').read_text(encoding='utf-8')
    assert '.home-workspace-section .card-grid {gap:10px;padding:12px 10px 14px;overflow:visible;' in css
