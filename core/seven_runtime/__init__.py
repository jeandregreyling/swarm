"""Seven standalone runtime service.

This package is the process boundary for Seven as ground zero: stdlib HTTP,
no Flask dependency, and no Ollama dependency for the default direct runtime.
"""

from .service import health_snapshot, run_server

__all__ = ["health_snapshot", "run_server"]
