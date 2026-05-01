"""core.records — Platinum layer per-record file storage + typed edges."""
from .store import (  # noqa: F401
    KINDS, RECORDS_ROOT, LEDGER_PATH, XREF_PATH, LINKS_DB,
    record_path, record_md_path,
    save_record, load_record, snapshot_all, mirror,
)
from .links import (  # noqa: F401
    Edge, INVERSES,
    link, unlink, outgoing, incoming, neighbours, all_links, count as link_count,
)
from .promote import promote, promotion_chain  # noqa: F401
from . import xref  # noqa: F401
from . import attachments  # noqa: F401

