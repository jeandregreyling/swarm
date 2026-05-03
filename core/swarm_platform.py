"""core.swarm_platform — runtime capability detection for the swarm.

Every deploy asks the same question: *which of the OS-dependent subsystems
can I use right now, and which must degrade?* This module answers it once,
honestly, with no import-time surprises.

Public surface::

    from core.swarm_platform import capabilities, summary
    caps = capabilities()   # full dict with boolean flags + hints
    rep  = summary()        # trimmed JSON-safe report for /api/platform

Design rules:
    * Every probe is wrapped — a missing binary or permission error returns
      ``False`` with a ``reason`` string, never an exception.
    * Results are cached for 30 s so dashboard polls don't thrash subprocess.
    * No probe writes to disk, spawns long-running children, or blocks > 1 s.
"""
from __future__ import annotations
import platform as _py_platform
# ...existing code...
