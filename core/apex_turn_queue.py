"""First-come, first-served slot for whole APEX turns.

APEX has one model slot. Without a turn-level queue, an operator message sent
while APEX is mid-turn grabbed the model between rounds or failed with
"model busy" and was never answered. Turns now wait their turn, bounded.
"""
from __future__ import annotations

import threading
import time


class TurnQueue:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._next_ticket = 0
        self._serving = 0
        self._abandoned: set[int] = set()

    def _advance(self) -> None:
        self._serving += 1
        while self._serving in self._abandoned:
            self._abandoned.discard(self._serving)
            self._serving += 1
        self._cond.notify_all()

    def acquire(self, timeout: float, on_wait=None) -> bool:
        """Wait in arrival order. on_wait(position) is called once if the slot is taken."""
        with self._cond:
            ticket = self._next_ticket
            self._next_ticket += 1
            if self._serving == ticket:
                return True
            if on_wait is not None:
                position = ticket - self._serving - sum(1 for t in self._abandoned if t < ticket)
                self._cond.release()
                try:
                    on_wait(position)
                finally:
                    self._cond.acquire()
            deadline = time.monotonic() + max(0.0, timeout)
            while self._serving != ticket:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._abandoned.add(ticket)
                    return False
                self._cond.wait(remaining)
            return True

    def release(self) -> None:
        with self._cond:
            self._advance()

    def busy(self) -> bool:
        with self._cond:
            return self._next_ticket != self._serving + len(self._abandoned)
