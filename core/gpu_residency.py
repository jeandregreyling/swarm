"""Opt-in residency lease foundation; no production loading paths use it yet."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
import math
from pathlib import Path
import threading
import time
from typing import Callable, Iterator, Sequence

logger = logging.getLogger(__name__)
GIB = 1024 ** 3


class ResidencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Resident:
    backend: str
    model: str
    device: str
    memory_bytes: int


class ResidencyController:
    """Adapters must report all runtimes and stop only the named owned model."""

    def __init__(
        self, lock_path: Path, snapshot: Callable[[], Sequence[Resident]],
        release: Callable[[str, str], None], available_memory: Callable[[], int],
        *, enabled: bool = False, timeout_s: float = 30,
        cpu_budget_bytes: int = 18 * GIB, reserve_bytes: int = 3 * GIB,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s < 0:
            raise ValueError("timeout_s must be finite and nonnegative")
        if cpu_budget_bytes <= 0 or reserve_bytes < 0:
            raise ValueError("memory budgets must be positive with a nonnegative reserve")
        self.lock_path = Path(lock_path)
        self.snapshot = snapshot
        self.release = release
        self.available_memory = available_memory
        self.enabled = enabled
        self.timeout_s = timeout_s
        self.cpu_budget_bytes = cpu_budget_bytes
        self.reserve_bytes = reserve_bytes
        self._thread_lock = threading.Lock()
    @contextmanager
    def _guard(self) -> Iterator[None]:
        try:
            import fcntl
        except ImportError as exc:
            raise ResidencyError("Enabled residency leases require POSIX file locking") from exc

        deadline = time.monotonic() + self.timeout_s
        if not self._thread_lock.acquire(timeout=self.timeout_s):
            raise ResidencyError("Residency queue timed out waiting for a thread")
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+b") as handle:
                while True:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise ResidencyError("Residency queue timed out waiting for a process")
                        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            self._thread_lock.release()

    def _observe(self) -> list[Resident]:
        residents = list(self.snapshot())
        identities = set()
        for item in residents:
            if not isinstance(item, Resident):
                raise ResidencyError("Backend returned an invalid resident record")
            if not item.backend or not item.model or item.device not in {"cpu", "gpu"}:
                raise ResidencyError("Backend returned an unknown model or device")
            if not isinstance(item.memory_bytes, int) or item.memory_bytes <= 0:
                raise ResidencyError("Backend must report positive resident memory bytes")
            identity = (item.backend, item.model)
            if identity in identities:
                raise ResidencyError("Backend returned a duplicate resident")
            identities.add(identity)
        return residents

    def _check_idle(self) -> None:
        residents = self._observe()
        for item in residents:
            if item.device == "gpu":
                raise ResidencyError(f"Unreleased GPU resident: {item.backend}/{item.model}")
            if (item.backend, item.model) != ("ollama", "fred-cpu:24b"):
                raise ResidencyError(f"Unbudgeted CPU resident: {item.backend}/{item.model}")
        if sum(item.memory_bytes for item in residents) > self.cpu_budget_bytes:
            raise ResidencyError("CPU resident exceeds its separate memory budget")
        available = self.available_memory()
        if not isinstance(available, int) or available < self.reserve_bytes:
            raise ResidencyError("Available host memory is below the required reserve")

    def _release_verified(self, backend: str, model: str) -> None:
        self.release(backend, model)
        deadline = time.monotonic() + self.timeout_s
        while True:
            remaining = [
                item for item in self._observe()
                if (item.backend, item.model) == (backend, model)
            ]
            if not remaining:
                self._check_idle()
                return
            if time.monotonic() >= deadline:
                raise ResidencyError(f"Release not confirmed: {backend}/{model}")
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))

    @contextmanager
    def lease(self, backend: str, model: str, *, cpu_backup: bool = False) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        if not backend.strip() or not model.strip():
            raise ValueError("backend and model are required")
        if cpu_backup and (backend, model) != ("ollama", "fred-cpu:24b"):
            raise ValueError("Only the verified CPU-only Fred assignment may remain resident")
        with self._guard():
            self._check_idle()
            logger.info("Residency lease acquired: %s/%s", backend, model)
            try:
                yield
            finally:
                if cpu_backup:
                    self._check_idle()
                else:
                    self._release_verified(backend, model)
                logger.info("Residency lease released: %s/%s", backend, model)
