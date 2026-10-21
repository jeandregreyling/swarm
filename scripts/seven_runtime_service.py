#!/usr/bin/env python3
"""Run Seven's standalone runtime service."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
UTILS = os.path.join(ROOT, "utils")
if UTILS not in sys.path:
    sys.path.insert(0, UTILS)

from core.seven_runtime.service import main


if __name__ == "__main__":
    raise SystemExit(main())
