"""core.seven.continuous — Seven's always-on learner.

Tails ``runtime/records/_ledger.jsonl`` and feeds every new entry into
``reasoning.learn``. Mirrors the existing ``stuck-job-sweep`` daemon
pattern in ``frontend/terminal.py``: a single daemon thread, no external
deps, safe-to-restart.

State
-----
    runtime/seven/ledger.offset
        Plain text byte offset of the last fully-processed line. Survives
        restarts so Seven doesn't re-learn the whole ledger every boot.

    runtime/seven/heartbeat.json
        Last known liveness signal — ``{ts, processed, last_eid, alive}``.
        Read by ``/api/seven/heartbeat``.

    seven_episodes table
        Each ledger line becomes one episode (``source='ledger'``).

Cadence
-------
    Polls every ``CONTINUOUS_POLL_S`` seconds (default 5). On startup it
    catches up from the last offset. Periodically (every
    ``CONSOLIDATE_EVERY_S`` seconds) it calls ``reasoning.consolidate()``
    to refresh derived beliefs (is_stale, is_hub, is_active).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from core.records.store import LEDGER_PATH, _SWARM_ROOT  # type: ignore
from . import reasoning as _rsn

CONTINUOUS_POLL_S = float(os.environ.get("SEVEN_CONTINUOUS_POLL_S", "5"))
CONSOLIDATE_EVERY_S = float(os.environ.get("SEVEN_CONSOLIDATE_EVERY_S", "300"))

SEVEN_RUNTIME = Path(_SWARM_ROOT) / "runtime" / "seven"
OFFSET_FILE = SEVEN_RUNTIME / "ledger.offset"
HEARTBEAT_FILE = SEVEN_RUNTIME / "heartbeat.json"

_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_state_lock = threading.Lock()
_last_state = {
    "alive": False,
    "started_at": None,
    "ts": None,
    "processed": 0,
    "last_eid": None,
    "last_event": None,
    "consolidations": 0,
    "errors": 0,
}


# ── offset I/O ──────────────────────────────────────────────────────────────

def _read_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text(encoding="utf-8").strip() or "0")
    except FileNotFoundError:
        return 0
    except Exception:
        return 0


def _write_offset(off: int) -> None:
    SEVEN_RUNTIME.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(int(off)), encoding="utf-8")


def _write_heartbeat() -> None:
    SEVEN_RUNTIME.mkdir(parents=True, exist_ok=True)
    with _state_lock:
        snap = dict(_last_state)
    HEARTBEAT_FILE.write_text(json.dumps(snap, default=str, indent=2), encoding="utf-8")


def heartbeat_snapshot() -> dict:
    """Read a fresh heartbeat from disk + in-process state."""
    disk = {}
    try:
        disk = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        disk = {}
    with _state_lock:
        live = dict(_last_state)
    live["disk"] = disk
    live["alive"] = bool(_thread and _thread.is_alive())
    return live


# ── one tick of work ────────────────────────────────────────────────────────

def _process_pending() -> int:
    """Read new ledger bytes since last offset, learn from each entry.
    Returns how many episodes were added this tick."""
    if not LEDGER_PATH.exists():
        return 0
    try:
        size = LEDGER_PATH.stat().st_size
    except OSError:
        return 0
    off = _read_offset()
    if off > size:
        # ledger truncated/rotated — reset
        off = 0
    if off == size:
        return 0

    added = 0
    last_eid = None
    last_event = None
    with LEDGER_PATH.open("r", encoding="utf-8") as f:
        f.seek(off)
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            try:
                res = _rsn.learn(event)
                last_eid = res.get("episode_id")
                last_event = event
                added += 1
            except Exception:
                with _state_lock:
                    _last_state["errors"] += 1
        new_off = f.tell()

    _write_offset(new_off)
    if added:
        with _state_lock:
            _last_state["processed"] += added
            _last_state["last_eid"] = last_eid
            _last_state["last_event"] = last_event
            _last_state["ts"] = time.time()
    return added


# ── thread loop ─────────────────────────────────────────────────────────────

def _loop() -> None:
    last_consolidate = 0.0
    with _state_lock:
        _last_state["alive"] = True
        _last_state["started_at"] = time.time()
        _last_state["ts"] = time.time()
    _write_heartbeat()

    while not _stop_event.is_set():
        try:
            _process_pending()
        except Exception:
            with _state_lock:
                _last_state["errors"] += 1

        now = time.time()
        if (now - last_consolidate) >= CONSOLIDATE_EVERY_S:
            try:
                _rsn.consolidate()
                with _state_lock:
                    _last_state["consolidations"] += 1
            except Exception:
                with _state_lock:
                    _last_state["errors"] += 1
            last_consolidate = now

        with _state_lock:
            _last_state["ts"] = time.time()
        try:
            _write_heartbeat()
        except Exception:
            pass

        _stop_event.wait(CONTINUOUS_POLL_S)

    with _state_lock:
        _last_state["alive"] = False
    _write_heartbeat()


# ── public start/stop ───────────────────────────────────────────────────────

def start() -> threading.Thread:
    """Idempotent. Spawns the daemon if not already running."""
    global _thread
    if _thread and _thread.is_alive():
        return _thread
    _stop_event.clear()
    SEVEN_RUNTIME.mkdir(parents=True, exist_ok=True)
    t = threading.Thread(target=_loop, name="seven-continuous", daemon=True)
    t.start()
    _thread = t
    return t


def stop(timeout: float = 2.0) -> None:
    _stop_event.set()
    if _thread:
        _thread.join(timeout=timeout)


def is_alive() -> bool:
    return bool(_thread and _thread.is_alive())


# ── one-shot catch-up (used at boot before thread starts, optional) ─────────

def catch_up() -> int:
    """Process all pending ledger bytes synchronously. Returns count."""
    return _process_pending()
