"""core/llm/pool.py — warm-pool with TTL, RAM ceiling, LRU eviction.

Every model that is loaded into memory by any driver is tracked here so the
Swarm can enforce a global RAM ceiling and evict the least-recently-used
model before a new one is admitted.

The pool is driver-agnostic: drivers call :func:`acquire` before serving a
request and :func:`release` when done. Idle entries past their TTL are evicted
by :func:`sweep`, which runs on a background thread.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import registry as _reg


RAM_CEILING_GB = float(os.environ.get("SEVEN_LLM_RAM_CEILING_GB", "24"))
SWEEP_INTERVAL_SECONDS = 30


@dataclass
class PoolEntry:
    name: str
    ram_gb: float
    ttl_seconds: int
    loaded_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    in_flight: int = 0
    evict_cb: Optional[Callable[[str], None]] = None


_LOCK = threading.RLock()
_ENTRIES: dict[str, PoolEntry] = {}
_SWEEP_THREAD: Optional[threading.Thread] = None
_STOP = threading.Event()


def _current_ram_gb() -> float:
    return sum(e.ram_gb for e in _ENTRIES.values())


def _evict_lru(need_gb: float) -> None:
    """Evict LRU entries until `need_gb` fits under the ceiling."""
    while _current_ram_gb() + need_gb > RAM_CEILING_GB:
        candidates = [e for e in _ENTRIES.values() if e.in_flight == 0]
        if not candidates:
            break  # can't evict anything in-flight
        victim = min(candidates, key=lambda e: e.last_used_at)
        _remove(victim.name)


def _remove(name: str) -> None:
    entry = _ENTRIES.pop(name, None)
    if entry and entry.evict_cb:
        try:
            entry.evict_cb(name)
        except Exception:
            pass


def acquire(name: str, ram_gb: Optional[float] = None, ttl_seconds: Optional[int] = None,
            evict_cb: Optional[Callable[[str], None]] = None) -> PoolEntry:
    """Mark a model as in-use, loading it into pool bookkeeping if needed."""
    with _LOCK:
        entry = _ENTRIES.get(name)
        if entry is None:
            meta = _reg.get(name)
            if ram_gb is None:
                ram_gb = meta.ram_gb if meta else 4.0
            if ttl_seconds is None:
                ttl_seconds = meta.ttl_seconds if meta else 300
            _evict_lru(ram_gb)
            entry = PoolEntry(name=name, ram_gb=ram_gb, ttl_seconds=ttl_seconds, evict_cb=evict_cb)
            _ENTRIES[name] = entry
        entry.in_flight += 1
        entry.last_used_at = time.time()
        return entry


def release(name: str) -> None:
    with _LOCK:
        entry = _ENTRIES.get(name)
        if not entry:
            return
        entry.in_flight = max(0, entry.in_flight - 1)
        entry.last_used_at = time.time()


def sweep(now: Optional[float] = None) -> int:
    """Evict entries past their TTL. Returns number evicted."""
    now = now or time.time()
    evicted = 0
    with _LOCK:
        for name, entry in list(_ENTRIES.items()):
            if entry.in_flight > 0:
                continue
            if now - entry.last_used_at >= entry.ttl_seconds:
                _remove(name)
                evicted += 1
    return evicted


def snapshot() -> list[dict]:
    with _LOCK:
        return [
            {
                "name": e.name,
                "ram_gb": e.ram_gb,
                "ttl_seconds": e.ttl_seconds,
                "loaded_at": e.loaded_at,
                "last_used_at": e.last_used_at,
                "in_flight": e.in_flight,
                "age_s": round(time.time() - e.loaded_at, 1),
            }
            for e in _ENTRIES.values()
        ]


def _sweeper() -> None:
    while not _STOP.wait(SWEEP_INTERVAL_SECONDS):
        try:
            sweep()
        except Exception:
            pass


def start_sweeper() -> None:
    global _SWEEP_THREAD
    if _SWEEP_THREAD and _SWEEP_THREAD.is_alive():
        return
    _STOP.clear()
    _SWEEP_THREAD = threading.Thread(target=_sweeper, name="seven-llm-pool-sweeper", daemon=True)
    _SWEEP_THREAD.start()


def stop_sweeper() -> None:
    _STOP.set()
