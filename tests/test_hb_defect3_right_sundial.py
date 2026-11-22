"""Tests for Defect 3: Right Sundial Services portal, 7-spoke Nectar ring alignment, Esc on Trace & Identity, active HB roster."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_services_portal_trace_esc_identity_roster_and_nectar_ring():
    srv = ROOT / 'frontend/static/js/views/services.js'
    toast = ROOT / 'frontend/static/js/core/toast.js'
    skills = ROOT / 'frontend/static/js/views/skills.js'
    css = (ROOT / 'frontend/static/css/diamond.css').read_text(encoding='utf-8')

    srv_src = srv.read_text(encoding='utf-8')
    assert 'document.body.appendChild(menu)' in srv_src
    assert "e.key !== 'Escape'" in srv_src

    toast_src = toast.read_text(encoding='utf-8')
    assert '__hbTraceEscBound' in toast_src and 'toggleTroubleshootPanel(false)' in toast_src

    skills_src = skills.read_text(encoding='utf-8')
    assert 'HB_ACTIVE_ROSTER' in skills_src and 'Shakira' in skills_src
    assert "if (e.key === 'Escape')" in skills_src

    assert '#dial-nectar-btn        { left: 120px; top: 39px;' in css

    for p in (srv, toast, skills):
        chk = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True)
        assert chk.returncode == 0, f'{p.name}: {chk.stderr}'
