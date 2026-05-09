"""Tests for audit Areas 5, 6, 7, 9, 10.

Covers operational, agent, frontend, dependency, and documentation checks.
All tests use file reads only — no DB, no network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


# ── Area 5 — Operations & Deployment ────────────────────────────────────────

class TestArea5Operations:
    """Systemd units, Makefile targets, deploy chain."""

    EXPECTED_SERVICES = [
        "swarm-terminal.service",
        "swarm-discord.service",
        "swarm-fridays.service",
        "swarm-telegram.service",
        "swarm-prewarm.service",
        "swarm-scheduler.service",
    ]

    def test_all_systemd_units_present(self):
        for svc in self.EXPECTED_SERVICES:
            assert (_ROOT / svc).is_file(), f"Missing systemd unit: {svc}"

    def test_makefile_has_deploy_target(self):
        mk = (_ROOT / "Makefile").read_text()
        assert "deploy:" in mk

    def test_makefile_has_bullshit_target(self):
        mk = (_ROOT / "Makefile").read_text()
        assert "bullshit:" in mk

    def test_makefile_has_excellent_target(self):
        mk = (_ROOT / "Makefile").read_text()
        assert "excellent:" in mk

    def test_makefile_deploy_runs_test_first(self):
        """deploy target must depend on test."""
        mk = (_ROOT / "Makefile").read_text()
        for line in mk.splitlines():
            if line.startswith("deploy:"):
                assert "test" in line, "deploy target should depend on test"
                break


# ── Area 6 — Agent Ecosystem ────────────────────────────────────────────────

class TestArea6Agents:
    """Agent directory structure and routing wiring."""

    def test_skill_intent_exists(self):
        assert (_ROOT / "agents" / "skill_intent.py").is_file()

    def test_skills_loop_exists(self):
        assert (_ROOT / "agents" / "skills_loop.py").is_file()

    def test_skill_intent_has_routing_function(self):
        src = (_ROOT / "agents" / "skill_intent.py").read_text()
        assert "message_likely_needs_skills" in src

    def test_agent_seven_directory_exists(self):
        assert (_ROOT / "agents" / "seven").is_dir()

    def test_minimum_agent_directories(self):
        """At least 15 agent directories should exist."""
        agent_dirs = [d for d in (_ROOT / "agents").iterdir() if d.is_dir() and d.name != "__pycache__"]
        assert len(agent_dirs) >= 15, f"Only {len(agent_dirs)} agent dirs found"


# ── Area 7 — Frontend & UI Standard ─────────────────────────────────────────

class TestArea7Frontend:
    """Terminal base template, XSS protection, wishlist tiles."""

    def test_terminal_base_exists(self):
        assert (_ROOT / "frontend" / "templates" / "terminal_base.html").is_file()

    def test_wishlist_status_attributes_present(self):
        src = (_ROOT / "frontend" / "templates" / "terminal_base.html").read_text()
        assert "data-wishlist-status" in src

    def test_dompurify_xss_protection(self):
        """Base template must include DOMPurify for XSS hardening."""
        src = (_ROOT / "frontend" / "templates" / "terminal_base.html").read_text()
        assert "DOMPurify" in src

    def test_safe_markdown_renderer(self):
        """Base template must use safeMarkdown, not raw marked.parse."""
        src = (_ROOT / "frontend" / "templates" / "terminal_base.html").read_text()
        assert "safeMarkdown" in src

    def test_no_unguarded_console_log_in_base(self):
        src = (_ROOT / "frontend" / "templates" / "terminal_base.html").read_text()
        assert "console.log" not in src

    def test_theme_engine_exists(self):
        assert (_ROOT / "frontend" / "theme_engine.py").is_file()


# ── Area 9 — Dependency & Runtime Health ────────────────────────────────────

class TestArea9Dependencies:
    """requirements.txt, pyproject.toml, runtime health."""

    def test_requirements_txt_exists(self):
        assert (_ROOT / "requirements.txt").is_file()

    def test_pyproject_toml_exists(self):
        assert (_ROOT / "pyproject.toml").is_file()

    def test_requires_python_311_or_higher(self):
        src = (_ROOT / "pyproject.toml").read_text()
        assert '>=3.11' in src or '>=3.12' in src

    def test_nohup_out_not_leaking_secrets(self):
        """nohup.out should be empty or not contain obvious secrets."""
        nohup = _ROOT / "nohup.out"
        if nohup.is_file():
            content = nohup.read_text(errors="ignore")
            for pattern in ("sk-", "ghp_", "gsk_", "hf_", "AIza", "PRIVATE KEY"):
                assert pattern not in content, f"nohup.out may contain secret: {pattern}"


# ── Area 10 — Documentation Continuity ──────────────────────────────────────

class TestArea10Documentation:
    """Key docs exist and are real content, not stubs."""

    REAL_CONTENT_DOCS = [
        "the-standard.md",
        "getting-started.md",
        "wishlist-pillars.md",
        "continuous-improvement.md",
    ]

    STUB_DOCS = [
        "DEVELOPER_GUIDE.md",
        "ARCHITECTURE.md",
        "FILE_STRUCTURE.md",
        "CODING_BIBLE.md",
        "AGENTS.md",
    ]

    def test_real_content_docs_are_substantial(self):
        """Key docs must be >20 lines (not stubs)."""
        for name in self.REAL_CONTENT_DOCS:
            path = _ROOT / "docs" / name
            assert path.is_file(), f"Missing doc: {name}"
            lines = len(path.read_text().splitlines())
            assert lines > 20, f"{name} looks like a stub ({lines} lines)"

    def test_stub_docs_have_studio_redirect(self):
        """Stubbed docs must at least mention Studio for discoverability."""
        for name in self.STUB_DOCS:
            path = _ROOT / "docs" / name
            if path.is_file():
                content = path.read_text().lower()
                assert "studio" in content, f"{name} is a stub but doesn't mention Studio"

    def test_security_md_exists(self):
        assert (_ROOT / "SECURITY.md").is_file()
