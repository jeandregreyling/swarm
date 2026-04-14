"""
db — Seven's Swarm database layer.

Backward-compatible re-exporter: every public symbol lives in its
domain module so callers can do fine-grained imports, but
``from db import *`` (or ``from database import *``) still works.
"""
from ._connection import *      # noqa: F401,F403
from ._schema    import *       # noqa: F401,F403
from .chat       import *       # noqa: F401,F403
from .memory     import *       # noqa: F401,F403
from .tickets    import *       # noqa: F401,F403
from .agents     import *       # noqa: F401,F403
from .auth       import *       # noqa: F401,F403
from .approvals  import *       # noqa: F401,F403
from .audit      import *       # noqa: F401,F403
from .timeline   import timeline_append, timeline_get  # noqa: F401

# Explicitly export private schema helpers needed by listener.py and other callers
from ._schema import _migrate_schema  # noqa: F401
