"""Tests for session 28 batch 16: README, /api/health, pre-commit hook,
first-run banner, make doctor, and the strengthened detector rules.

Per-batch isolated tests. Run with:
    timeout 30 .venv/bin/python -m pytest tests/test_session28_batch16.py -x -q
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# ROOT must be first so frontend/blueprints/agents.py does not shadow the
# top-level agents/ package.
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / 'frontend'))


# ── README ──────────────────────────────────────────────────────────────

def test_readme_is_real():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert len(text) > 1500, 'README looks like a stub'
    for needle in ('make excellent', 'the-standard', 'Seven', 'pillars', '/api/health'):
        assert needle.lower() in text.lower(), f'README missing: {needle}'


def test_readme_no_capture_only_anywhere():
    text = (ROOT / 'README.md').read_text(encoding='utf-8').lower()
    assert 'capture only' not in text


# ── /api/health blueprint shape ─────────────────────────────────────────

def test_health_blueprint_module_imports_and_has_routes():
    from blueprints import health as h
    assert hasattr(h, 'health_bp')
    src = (ROOT / 'frontend' / 'blueprints' / 'health.py').read_text()
    assert "/api/health" in src
    assert "_composite_stamp" in src
    assert "_pillar_summaries" in src


def test_health_endpoint_response_shape(monkeypatch):
    """Build a tiny Flask app with just the health blueprint and verify shape."""
    from flask import Flask
    from blueprints.health import health_bp
    app = Flask(__name__)
    app.config['FAILED_BLUEPRINTS'] = []
    app.register_blueprint(health_bp)
    with app.test_client() as c:
        rv = c.get('/api/health')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'stamp' in data and data['stamp'] in ('GREEN', 'AMBER', 'RED')
        assert 'build' in data and 'detector_stamp' in data['build']
        assert 'pillars' in data
        assert isinstance(data['pillars'], dict)
        assert 'learnings' in data
        assert 'uptime_s' in data


# ── Pre-commit hook script ──────────────────────────────────────────────

def test_install_hooks_script_exists_and_executable():
    p = ROOT / 'scripts' / 'install-hooks.sh'
    assert p.exists()
    mode = p.stat().st_mode
    assert mode & stat.S_IXUSR, 'install-hooks.sh not executable'
    text = p.read_text()
    assert 'pre-commit' in text
    assert 'bullshit_detector' in text
    assert '--no-verify' in text


# ── make doctor ─────────────────────────────────────────────────────────

def test_doctor_module_imports_and_runs_minimal():
    """ops.doctor should import without side-effects and expose a main()."""
    from ops import doctor
    assert callable(doctor.main)
    # A subset that does not run pytest internally:
    assert callable(doctor.run_detector)
    assert callable(doctor.probe_health)
    assert callable(doctor.db_counts)


def test_make_doctor_target_present():
    text = (ROOT / 'Makefile').read_text()
    assert 'doctor:' in text
    assert 'ops.doctor' in text
    assert 'health:' in text
    assert 'hooks:' in text


# ── First-run banner ────────────────────────────────────────────────────

def test_home_banner_js_exists():
    p = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'home_banner.js'
    assert p.exists()
    text = p.read_text()
    assert '/api/wishlist/summary' in text
    assert 'first-run-banner' in text
    assert 'localStorage' in text


def test_terminal_template_loads_banner_and_has_div():
    p = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
    text = p.read_text()
    assert 'home_banner.js' in text
    assert 'id="first-run-banner"' in text
    assert 'first-run-banner-dismiss' in text


# ── Detector strengthening ──────────────────────────────────────────────

def test_detector_has_capture_only_desc_and_vapor_rules():
    src = (ROOT / 'ops' / 'bullshit_detector.py').read_text()
    assert 'CAPTURE_ONLY_DESC' in src
    assert 'VAPOR_LANGUAGE' in src
    assert 'detector:ignore' in src


def test_detector_no_warnings_on_repo():
    """The repo must scan clean — 0 critical, 0 warnings."""
    from ops.bullshit_detector import scan
    d = scan()
    assert d['by_severity']['critical'] == 0, [h for h in d['hits'] if h['severity'] == 'critical']
    assert d['by_severity']['warning'] == 0, [h for h in d['hits'] if h['severity'] == 'warning']


def test_detector_summary_includes_files_scanned():
    from ops.bullshit_detector import summary_for_seven
    s = summary_for_seven()
    assert s['files_scanned'] > 0


# ── Tile descriptions match active-v0 reality ───────────────────────────

def test_tile_descriptions_have_no_capture_only():
    text = (ROOT / 'frontend' / 'templates' / 'terminal_base.html').read_text().lower()
    # Must not mention "capture only" anywhere — the rule itself catches this
    # but pin it as a test too.
    assert 'capture only' not in text


# ── No bare except: anywhere in production paths ────────────────────────

def test_no_bare_except_in_shipped_code():
    """Bare excepts allowed only in tests/Archives/sandpits."""
    bad = []
    for fp in (ROOT / 'core').rglob('*.py'):
        if re.search(r'^\s*except\s*:\s*(#.*)?$', fp.read_text(encoding='utf-8', errors='replace'), re.MULTILINE):
            bad.append(str(fp))
    for fp in (ROOT / 'lib').rglob('*.py'):
        if re.search(r'^\s*except\s*:\s*(#.*)?$', fp.read_text(encoding='utf-8', errors='replace'), re.MULTILINE):
            bad.append(str(fp))
    assert not bad, f'bare except found in: {bad}'


# ── Studio.js no longer has "coming soon" stubs ─────────────────────────

def test_studio_js_no_vapor():
    p = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'studio.js'
    text = p.read_text().lower()
    assert 'coming soon' not in text
    # Real wiring present:
    assert '/api/chat/jobs/status' in text
    assert '/api/seven/episodes' in text
    assert '/api/chat/agents/health' in text
