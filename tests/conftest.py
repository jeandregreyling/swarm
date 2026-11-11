"""Global pytest configuration for the Swarm test suite.

Key guarantees provided here:
1. SWARM_DB_PATH is redirected to an isolated per-session temp file so tests
   never touch the live swarm_memory.db (and do not fail with "database is
   locked" when the app server is running in a parallel WSL process).
2. PYTHONUTF8=1 is ensured at process level so read_text() on JS/HTML files
   containing multi-byte characters works correctly on Windows.
"""

from __future__ import annotations

import os as _os

# Tests must not depend on which agent holds the worker seat in runtime/worker_agent.txt.
_os.environ.setdefault('SWARM_WORKER_AGENT', 'fred')
_os.environ.setdefault('SWARM_WORKER_MODEL', 'mistral-small:24b')

import os
import tempfile

def pytest_ignore_collect(collection_path, config):
    """Keep the standalone triage smoke script from mutating pytest's process."""
    if collection_path.name == "test_triage_queue_dryrun.py":
        return True
    return None

# ── UTF-8 mode ────────────────────────────────────────────────────────────────
# pathlib.read_text() falls back to the locale codec on Windows (cp1252).
# Setting this env var here ensures it applies even if the test module reads
# files at import time (before fixtures run).
os.environ.setdefault("PYTHONUTF8", "1")

# ── Isolated test database ────────────────────────────────────────────────────
# Create a single temp DB file for the entire test session.  We keep it on
# disk (not :memory:) because some tests use multiple connections.  The file
# is cleaned up automatically when the process exits (NamedTemporaryFile with
# delete=True on POSIX; on Windows we use delete=False and remove in the
# session-scoped fixture below so the handle is released first).

_TEST_DB = tempfile.NamedTemporaryFile(
    prefix="swarm_test_",
    suffix=".db",
    delete=False,
)
_TEST_DB.close()

os.environ["SWARM_DB_PATH"] = _TEST_DB.name
_TEST_AGENT_IDENTITIES = tempfile.TemporaryDirectory(prefix="swarm_test_identities_")
os.environ["HUMMINGBIRD_AGENT_STATE"] = _TEST_AGENT_IDENTITIES.name
os.environ["SWARM_VORTEX_LEDGER_DISABLED"] = "1"
_TEST_HF_MIRROR = tempfile.TemporaryDirectory(prefix="swarm_test_hf_mirror_")
os.environ["HUMMINGBIRD_HF_MIRROR_ROOT"] = _TEST_HF_MIRROR.name
os.environ["HUMMINGBIRD_HF_TEXT_INDEX"] = os.path.join(_TEST_HF_MIRROR.name,"text.sqlite")
_TEST_HB_LOCKS = tempfile.TemporaryDirectory(prefix="swarm_test_hb_locks_")
os.environ["HUMMINGBIRD_LOCK_DIR"] = _TEST_HB_LOCKS.name
_TEST_VORTEX_BACKUPS = tempfile.TemporaryDirectory(prefix="swarm_test_vortex_")
os.environ["SWARM_VORTEX_BACKUP_ROOT"] = _TEST_VORTEX_BACKUPS.name


_TEST_LLAMA_LOCK = os.path.join(tempfile.gettempdir(), f"swarm_test_llama_{os.getpid()}.lock")
_TEST_LLAMA_STATE = os.path.join(tempfile.gettempdir(), f"swarm_test_llama_{os.getpid()}.state.json")
os.environ.setdefault("SEVEN_LLAMA_LOCK_PATH", _TEST_LLAMA_LOCK)
os.environ.setdefault("SEVEN_LLAMA_STATE_PATH", _TEST_LLAMA_STATE)
os.environ.setdefault("SEVEN_LLAMA_SYSTEMD_SCOPE", "0")
# Keep the model registry hermetic: do not import the machine's Ollama store.
os.environ.setdefault("SWARM_OLLAMA_STORE", "")

import pytest


@pytest.fixture(autouse=True)
def _isolate_owner_apex_grants(tmp_path, monkeypatch):
    """Host standing grants must never authorize edits during unrelated tests."""
    from core import apex_permissions
    monkeypatch.setattr(apex_permissions, 'POLICY_PATH', tmp_path / 'absent-owner-policy.json')


@pytest.fixture(autouse=True)
def _isolate_live_llama_servers(monkeypatch):
    """Never let tests discover, reuse or kill the machine's real llama-servers."""
    from core.seven_llm import llama_server

    monkeypatch.setattr(llama_server, "_foreign_servers", lambda: [])
    monkeypatch.setattr(llama_server, "_vram_free_gb", lambda: None)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Remove the isolated test DB after all tests complete."""
    for path in (_TEST_DB.name, _TEST_LLAMA_LOCK, _TEST_LLAMA_STATE):
        try:
            os.unlink(path)
        except OSError:
            pass
