"""core.hive.self_sampler — leader-side daemon that samples THIS host.

Lets the Hive leader populate the registry with its own telemetry on a
tick, so the Monitor panel always shows at least one live node — the
leader itself — without an external agent.

Started lazily from frontend.terminal during boot. Safe to call multiple
times; only one thread is spawned per process.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from .local_node import build_local_telemetry, get_local_node
from .registry import get_registry

_LOG = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 30.0

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()


def _sampler_loop(interval: float) -> None:
    node = get_local_node()
    _LOG.info('hive self-sampler started node=%s interval=%.0fs',
              node.node_id, interval)
    while not _stop.is_set():
        try:
            payload = build_local_telemetry(node_id=node.node_id)
            reg = get_registry()
            reg.record_telemetry(payload)
        except Exception:
            _LOG.exception('self-sampler tick failed')
        # interruptible wait so SIGTERM exits within ~1s
        _stop.wait(interval)
    _LOG.info('hive self-sampler stopped')


def start(interval: float | None = None) -> threading.Thread | None:
    """Start the self-sampler thread once. Returns the thread (or None if disabled)."""
    global _thread
    if os.environ.get('SWARM_HIVE_DISABLE_SELF_SAMPLER', '').strip() in ('1', 'true', 'TRUE'):
        _LOG.info('hive self-sampler disabled via env')
        return None
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        _stop.clear()
        env_interval = os.environ.get('SWARM_HIVE_SELF_INTERVAL', '').strip()
        if interval is None:
            try:
                interval = float(env_interval) if env_interval else _DEFAULT_INTERVAL
            except ValueError:
                interval = _DEFAULT_INTERVAL
        interval = max(5.0, float(interval))
        t = threading.Thread(
            target=_sampler_loop,
            args=(interval,),
            name='hive-self-sampler',
            daemon=True,
        )
        t.start()
        _thread = t
        return t


def stop(timeout: float = 2.0) -> None:
    """Signal the sampler to exit and wait briefly."""
    global _thread
    _stop.set()
    t = _thread
    if t is not None:
        t.join(timeout=timeout)
    _thread = None


def is_running() -> bool:
    t = _thread
    return bool(t and t.is_alive())
