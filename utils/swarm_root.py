"""
utils/swarm_root.py — Central SWARM_ROOT resolution (A.6.3)
═══════════════════════════════════════════════════════════
Single source of truth for the swarm installation root.

Resolution order:
  1. SWARM_ROOT environment variable (highest priority)
  2. Auto-detect from this file's location (utils/swarm_root.py → parent)

Usage:
    from utils.swarm_root import SWARM_ROOT
"""
import os

SWARM_ROOT = os.environ.get(
    'SWARM_ROOT',
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
