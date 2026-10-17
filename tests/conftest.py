"""Global pytest configuration for the Swarm test suite.

Key guarantees provided here:
1. SWARM_DB_PATH is redirected to an isolated per-session temp file so tests
   never touch the live swarm_memory.db (and do not fail with "database is
   locked" when the app server is running in a parallel WSL process).
2. PYTHONUTF8=1 is ensured at process level so read_text() on JS/HTML files
   containing multi-byte characters works correctly on Windows.
"""

from __future__ import annotations

import os
import tempfile

# This standalone smoke script stubs global modules at import time; it is not a pytest test.
collect_ignore = ["test_triage_queue_dryrun.py"]

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


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Remove the isolated test DB after all tests complete."""
    try:
        os.unlink(_TEST_DB.name)
    except OSError:
        pass
