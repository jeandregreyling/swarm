"""Cache-bust assertions for terminal_base.html (S-CAAD1B6D9C).

Every <script src="/static/js/views/*.js"> in terminal_base.html must
include ?v={{ ASSET_VERSION }} so a deploy invalidates the browser cache
without manual ?v=N bumps. The Jinja variable is provided by a context
processor in frontend/terminal.create_app().
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "frontend" / "templates" / "terminal_base.html"


def test_template_exists():
    assert TEMPLATE.exists(), f"missing {TEMPLATE}"


def test_every_view_script_has_asset_version_query():
    src = TEMPLATE.read_text(encoding="utf-8")
    tags = re.findall(r'<script\s+src="(/static/js/views/[^"]+)"', src)
    assert tags, "no view script tags found in terminal_base.html"
    bad = [t for t in tags if "?v={{ ASSET_VERSION }}" not in t]
    assert not bad, (
        "the following <script> tags don't use the global cache-bust "
        f"token: {bad}"
    )


def test_no_legacy_hardcoded_version_for_view_scripts():
    """Reject the old pattern ?v=2, ?v=30 etc. so contributors don't
    accidentally regress to manual cache-bust bumps."""
    src = TEMPLATE.read_text(encoding="utf-8")
    bad = re.findall(r'<script\s+src="(/static/js/views/[^"]+\?v=\d+)"', src)
    assert not bad, f"manual ?v=NN found on: {bad}"


def test_compute_asset_version_returns_non_empty(monkeypatch):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(ROOT / "frontend") not in sys.path:
        sys.path.insert(0, str(ROOT / "frontend"))
    monkeypatch.delenv("SWARM_ASSET_VERSION", raising=False)
    from frontend import terminal as t
    v = t._compute_asset_version()
    assert isinstance(v, str) and v.strip()


def test_compute_asset_version_respects_env(monkeypatch):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(ROOT / "frontend") not in sys.path:
        sys.path.insert(0, str(ROOT / "frontend"))
    monkeypatch.setenv("SWARM_ASSET_VERSION", "deploy-42")
    from frontend import terminal as t
    assert t._compute_asset_version() == "deploy-42"
