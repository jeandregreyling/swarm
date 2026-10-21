"""core.seven — Seven IS the system.

Seven is the always-on substrate of the swarm: perception, memory,
reasoning, and continuous learning all in one local-only package.
Surfaces (Spotlight, Studio, Vortex, Diamond, agents, sparkles) consume
this package; they do not stitch blackboard + record_links + steps
themselves.

Authority: propose-only. Seven observes, remembers, reasons, proposes.
It never mutates state on its own.

Entry points
------------
Perception:   ``observe``, ``related``, ``recent``, ``open_steps``, ``stats``
Memory:       ``memory`` submodule + ``concepts`` for KC seed loading
Reasoning:    ``explain``, ``decide``, ``learn``, ``consolidate``
Continuous:   ``start_continuous``, ``stop_continuous``, ``heartbeat``
Suggest:      ``suggestions`` (propose-only nudges)
"""

from .perception import observe, related, recent, open_steps, stats  # noqa: F401
from .suggest import suggestions  # noqa: F401
from . import memory, concepts  # noqa: F401
from .reasoning import explain, decide, learn, consolidate  # noqa: F401
from .continuous import (  # noqa: F401
    start as start_continuous,
    stop as stop_continuous,
    is_alive as continuous_alive,
    heartbeat_snapshot as heartbeat,
    catch_up as continuous_catch_up,
)


def boot(*, seed_concepts: bool = True, start_learner: bool = True) -> dict:
    """One-call brain init for Flask startup.

    - Ensures memory schema exists.
    - Seeds ``seven_concepts`` from ``docs/seven/*.md`` (only if empty).
    - Starts the continuous daemon thread, which catches up the ledger
      asynchronously on its first tick (so Flask startup is not blocked
      by ledger replay).

    Returns a small dict with what it did, suitable for logging.
    """
    out = {"schema": False, "seeded_concepts": 0, "thread": False}
    memory.ensure_schema()
    out["schema"] = True
    if seed_concepts:
        out["seeded_concepts"] = concepts.ensure_seeded()
    if start_learner:
        start_continuous()
        out["thread"] = continuous_alive()
    return out


__all__ = [
    "observe", "related", "recent", "open_steps", "stats", "suggestions",
    "memory", "concepts",
    "explain", "decide", "learn", "consolidate",
    "start_continuous", "stop_continuous", "continuous_alive",
    "heartbeat", "continuous_catch_up",
    "boot",
]
