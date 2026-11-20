"""Media data location, independent of the installation/source location.

The default preserves existing production state and artifact URLs. Tests and
separate deployments can redirect all media data before importing consumers.
"""
import os
from pathlib import Path
from utils.swarm_root import SWARM_ROOT

MEDIA_STORAGE_ROOT = Path(os.environ.get('HUMMINGBIRD_MEDIA_ROOT') or SWARM_ROOT).expanduser().resolve()
