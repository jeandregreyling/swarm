#!/usr/bin/env python3
"""WSL → Windows-host Ollama bridge.

Binds 127.0.0.1:11434 inside WSL and forwards to the Windows host's Ollama on
the same port (auto-detected from the default route, overridable via
SWARM_OLLAMA_UPSTREAM=<host>:<port>).

Exits cleanly if not running under WSL, if local 11434 is already serving
Ollama, or if the upstream is unreachable. Safe to run unconditionally from
seven.sh.
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import urllib.request

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 11434


def _is_wsl() -> bool:
    try:
        with open("/proc/version", "r", encoding="utf-8") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _detect_windows_host() -> str | None:
    override = os.environ.get("SWARM_OLLAMA_UPSTREAM")
    if override:
        return override
    try:
        out = subprocess.check_output(
            ["ip", "route", "show", "default"], text=True, timeout=2
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "default":
            return f"{parts[2]}:11434"
    return None


def _probe_http(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


def _make_handler(upstream_host: str, upstream_port: int):
    async def handler(
        client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        try:
            server_reader, server_writer = await asyncio.open_connection(
                upstream_host, upstream_port
            )
        except OSError as exc:
            print(f"[bridge] upstream connect failed: {exc}", file=sys.stderr)
            client_writer.close()
            return
        await asyncio.gather(
            _pipe(client_reader, server_writer),
            _pipe(server_reader, client_writer),
        )

    return handler


async def _serve(upstream: str) -> int:
    host, _, port_s = upstream.partition(":")
    port = int(port_s or 11434)
    try:
        server = await asyncio.start_server(
            _make_handler(host, port), LISTEN_HOST, LISTEN_PORT
        )
    except OSError as exc:
        print(f"[bridge] cannot bind {LISTEN_HOST}:{LISTEN_PORT}: {exc}", file=sys.stderr)
        return 1
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    print(f"[bridge] WSL→Windows Ollama bridge: {addrs} → {host}:{port}")
    async with server:
        await server.serve_forever()
    return 0


def main() -> int:
    if not _is_wsl():
        print("[bridge] not running under WSL; nothing to do.")
        return 0

    # If something already serves Ollama locally, do nothing.
    if _probe_http(f"http://{LISTEN_HOST}:{LISTEN_PORT}/api/tags", timeout=1.0):
        print("[bridge] local 11434 already serving Ollama; skipping.")
        return 0

    upstream = _detect_windows_host()
    if not upstream:
        print("[bridge] could not detect Windows host gateway.", file=sys.stderr)
        return 2

    host, _, port_s = upstream.partition(":")
    port = int(port_s or 11434)
    try:
        with socket.create_connection((host, port), timeout=2.0):
            pass
    except OSError as exc:
        print(f"[bridge] upstream {host}:{port} unreachable: {exc}", file=sys.stderr)
        return 3

    if not _probe_http(f"http://{host}:{port}/api/tags", timeout=2.0):
        print(f"[bridge] upstream {host}:{port} reachable but no Ollama API.", file=sys.stderr)
        return 4

    try:
        return asyncio.run(_serve(upstream))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
