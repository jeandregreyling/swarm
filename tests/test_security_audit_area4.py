"""Tests for Area 4 — Security & Secrets audit fixes.

Covers:
- kill_switch.py uses correct DB import path (utils.db._connection)
- killswitch.sh no longer has hardcoded /home/seven/swarm
- secret_scan.py patterns cover key providers
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


# ── kill_switch.py import path ──────────────────────────────────────────────

def test_kill_switch_uses_correct_db_import():
    """core/kill_switch.py must import from utils.db._connection, not utils.database."""
    src = (_ROOT / "core" / "kill_switch.py").read_text()
    assert "from utils.database" not in src, "kill_switch.py still uses broken utils.database shim"
    assert "from utils.db._connection import get_connection" in src


def test_kill_switch_no_hardcoded_path():
    """core/kill_switch.py must not contain hardcoded /home/seven/swarm."""
    src = (_ROOT / "core" / "kill_switch.py").read_text()
    assert "/home/seven/swarm" not in src


# ── killswitch.sh ───────────────────────────────────────────────────────────

def test_killswitch_sh_no_hardcoded_path():
    """killswitch.sh must not contain hardcoded /home/seven/swarm."""
    src = (_ROOT / "killswitch.sh").read_text()
    assert "/home/seven/swarm" not in src


def test_killswitch_sh_uses_swarm_root():
    """killswitch.sh should use SWARM_ROOT or dirname-based resolution."""
    src = (_ROOT / "killswitch.sh").read_text()
    assert "SWARM_ROOT" in src


# ── secret_scan.py coverage ─────────────────────────────────────────────────

def test_secret_scan_covers_key_providers():
    """scripts/secret_scan.py must have patterns for critical token providers."""
    src = (_ROOT / "scripts" / "secret_scan.py").read_text()
    for provider in ("github", "openai", "anthropic", "private-key"):
        assert provider in src, f"secret_scan.py missing pattern for {provider}"


# ── .gitignore coverage ────────────────────────────────────────────────────

def test_gitignore_blocks_env_files():
    src = (_ROOT / ".gitignore").read_text()
    assert ".env" in src
    assert ".env.*" in src or ".env.agents" in src


def test_gitignore_blocks_credential_files():
    src = (_ROOT / ".gitignore").read_text()
    assert "*_credentials.json" in src
    assert "*_token.json" in src


def test_gitignore_blocks_databases():
    src = (_ROOT / ".gitignore").read_text()
    assert "*.db" in src
