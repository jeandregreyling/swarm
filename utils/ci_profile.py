"""utils.ci_profile — CI-friendly no-network integration profile.

S-D277FF5AFC. Provides ``enable_no_network()`` / ``disable_no_network()``
that monkey-patch ``socket.socket.connect`` to raise ``NetworkBlocked``
for any non-loopback destination. Tests and CI runs that must not touch
the public internet enable the profile during setup.

Loopback (127.0.0.0/8 + ::1) is always allowed so in-process Flask
test_clients and SQLite-over-localhost continue to work.
"""
from __future__ import annotations

import socket
from typing import Any, Optional


class NetworkBlocked(RuntimeError):
    """Raised when CI profile is active and a non-loopback connect is
    attempted. Caller code must treat this as an environmental failure
    (the test or CI step is wrong, not the system under test)."""


_ORIGINAL_CONNECT: Optional[Any] = None
_ORIGINAL_CONNECT_EX: Optional[Any] = None


def _is_loopback(addr: tuple) -> bool:
    try:
        host = addr[0]
    except Exception:
        return False
    if not host:
        return False
    if host in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
        return True
    if isinstance(host, str) and host.startswith('127.'):
        return True
    return False


def enable_no_network() -> None:
    """Install the connect() guard. Safe to call repeatedly."""
    global _ORIGINAL_CONNECT, _ORIGINAL_CONNECT_EX
    if _ORIGINAL_CONNECT is not None:
        return
    _ORIGINAL_CONNECT = socket.socket.connect
    _ORIGINAL_CONNECT_EX = socket.socket.connect_ex

    def guarded_connect(self, address):
        if not _is_loopback(address):
            raise NetworkBlocked(
                f"CI no-network profile blocked outbound connect to {address}"
            )
        return _ORIGINAL_CONNECT(self, address)

    def guarded_connect_ex(self, address):
        if not _is_loopback(address):
            raise NetworkBlocked(
                f"CI no-network profile blocked outbound connect_ex to {address}"
            )
        return _ORIGINAL_CONNECT_EX(self, address)

    socket.socket.connect = guarded_connect  # type: ignore[assignment]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[assignment]


def disable_no_network() -> None:
    """Restore the original connect()s. Safe to call repeatedly."""
    global _ORIGINAL_CONNECT, _ORIGINAL_CONNECT_EX
    if _ORIGINAL_CONNECT is None:
        return
    socket.socket.connect = _ORIGINAL_CONNECT  # type: ignore[assignment]
    if _ORIGINAL_CONNECT_EX is not None:
        socket.socket.connect_ex = _ORIGINAL_CONNECT_EX  # type: ignore[assignment]
    _ORIGINAL_CONNECT = None
    _ORIGINAL_CONNECT_EX = None


__all__ = ["NetworkBlocked", "enable_no_network", "disable_no_network"]
