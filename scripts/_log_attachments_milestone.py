"""One-shot milestone log for the attachments slice."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.studio_milestone import log_milestone

STORY = """Goal:
  Give every record kind a stable, dedupe-by-content way to attach
  binary blobs (screenshots, PDFs, .eml originals, log artefacts)
  without ever colliding on filenames or storing the same bytes twice.

What we built:
  - core/records/attachments.py: tiny content-addressed store.
      put(bytes, ext) -> sha256 hex (idempotent, atomic write via .tmp + os.replace)
      find(sha256), exists(sha256), path(sha256, ext), put_file(path)
      Layout: runtime/attachments/<sha256[:2]>/<sha256>.<ext>
  - HTTP surface in frontend/blueprints/knowledge_bp.py:
      POST /api/records/attachments        — multipart "file" or raw bytes; returns sha256
      GET  /api/records/attachments/<sha>  — streams the bytes back, 404 on miss
  - 12th platinum self-test invariant: check_attachments_store
      (creates the dir, round-trips a probe, asserts find() locates it)
  - .gitignore now ignores runtime/attachments/ alongside runtime/records/.

How to verify (proven this slice):
  - curl -s -X POST -F "file=@README.md" /api/records/attachments → 200, returns sha256
  - curl -s /api/records/attachments/<sha> → 200, byte-exact match (cmp -s = silent)
  - python3 scripts/architecture_self_test.py → 12 checks, 12 pass

Why this matters:
  Records can now reference attachments by hash instead of fragile
  filenames. Same image uploaded twice = one file on disk. Records tab
  and Files tile will render attachment previews directly from the
  hash without round-tripping through the DB.

Still open: Records tab UI, Files tile, PACKET-07 slices."""

log_milestone(
    packet="PACKET-08",
    title="Attachments — content-addressed binary store live",
    story=STORY,
    status="done",
)
print("ok")
