"""Content-addressed binary attachment store.

Layout:  runtime/attachments/<sha256[:2]>/<sha256>.<ext>

- Idempotent: storing the same bytes twice is a no-op.
- Caller-supplied extension is sanitised; default ".bin".
- Best-effort. Never raises on disk errors except where a caller asks.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Union

# resolve runtime/attachments/ relative to repo root (parent of core/)
_ROOT = Path(__file__).resolve().parent.parent.parent
ATTACHMENTS_ROOT: Path = _ROOT / "runtime" / "attachments"

_EXT_OK = re.compile(r"^[A-Za-z0-9]{1,12}$")


def _safe_ext(ext: Optional[str]) -> str:
    if not ext:
        return "bin"
    e = ext.lstrip(".").strip().lower()
    return e if _EXT_OK.match(e) else "bin"


def _shard(sha256: str) -> Path:
    return ATTACHMENTS_ROOT / sha256[:2]


def path(sha256: str, ext: str = "bin") -> Path:
    """Return the on-disk path for a given hash + extension.

    Does NOT verify the file exists.
    """
    return _shard(sha256) / f"{sha256}.{_safe_ext(ext)}"


def find(sha256: str) -> Optional[Path]:
    """Find an existing attachment by hash regardless of extension."""
    shard = _shard(sha256)
    if not shard.is_dir():
        return None
    for p in shard.glob(f"{sha256}.*"):
        if p.is_file():
            return p
    return None


def exists(sha256: str) -> bool:
    return find(sha256) is not None


def put(data: Union[bytes, bytearray, memoryview], ext: Optional[str] = None) -> str:
    """Store bytes; return the sha256 hex digest. Idempotent."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("attachments.put expects bytes-like input")
    blob = bytes(data)
    digest = hashlib.sha256(blob).hexdigest()
    target = path(digest, ext or "bin")
    if target.exists():
        return digest
    # if the same hash is already present under a different extension, reuse it
    existing = find(digest)
    if existing is not None:
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)
    return digest


def put_file(src_path: Union[str, os.PathLike]) -> str:
    p = Path(src_path)
    ext = p.suffix.lstrip(".") or "bin"
    return put(p.read_bytes(), ext=ext)


__all__ = [
    "ATTACHMENTS_ROOT",
    "path",
    "find",
    "exists",
    "put",
    "put_file",
]
