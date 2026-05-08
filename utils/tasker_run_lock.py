"""utils.tasker_run_lock — per-task in-process lock for run-now actions.

S-941A9C1A0A — concurrency probe for Tasker run-now. Prevents two
concurrent "run-now" presses from kicking the same task twice in
parallel (which historically duplicated outbound emails / shell jobs).

Usage::

    from utils.tasker_run_lock import try_run

    with try_run(task_id) as got_lock:
        if got_lock:
            # safe to execute the task body
            ...
        else:
            # another thread is already running this task_id
            return {"ok": False, "reason": "task already running"}

The lock is process-local; for cross-process serialisation use the
``scheduled_tasks`` row-state machine on top of this.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Dict, Iterator

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(task_id: str) -> threading.Lock:
    with _locks_guard:
        lk = _locks.get(task_id)
        if lk is None:
            lk = threading.Lock()
            _locks[task_id] = lk
        return lk


@contextmanager
def try_run(task_id: str) -> Iterator[bool]:
    """Yield True if the lock was acquired (caller may run), else False."""
    lk = _lock_for(task_id)
    got = lk.acquire(blocking=False)
    try:
        yield got
    finally:
        if got:
            lk.release()


def reset() -> None:
    """Drop every per-task lock. Test-only."""
    with _locks_guard:
        _locks.clear()


__all__ = ["try_run", "reset"]
