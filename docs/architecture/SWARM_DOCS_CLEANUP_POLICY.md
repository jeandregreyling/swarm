# swarm_docs Cleanup Policy

**Status**: Decided — keep tracked, regenerate-in-place, archive via Studio.
**Closes**: STEP-TRACKED-SWARM-DOCS-CLEANUP
**Owner**: Seven (governance), Twenty/Librarian (publication).
**Last reviewed**: 2026-04-30 (Batch Y.15+).

## Context

`swarm_docs/` carries 33 tracked artefacts:

- `00_index.docx` … `09_roadmap.docx` — chapter-style operator/integrator manual.
- `swarm_flow_v3.docx` + `swarm_flow_v3.html` — flow diagram exports.
- `SYSTEM_INDEX.md`, `SYSTEM_LANDSCAPE.json` — generated landscape inventory.
- `html/` and `xml/` — HTML/XML export mirrors of the same chapters.

These are publication outputs of `scripts/build_swarm_docs.py` (and its
predecessors). Earlier sessions flagged them as "tracked generated outputs that
were not deleted as housekeeping" — the open question was whether to
**untrack**, **regenerate** on demand, or **archive** them.

## Decision

**Keep tracked, regenerate-in-place, archive via Studio.**

1. **Keep tracked** — these documents are the only operator-facing manual
   shipped with the repo. Untracking would delete them on the next
   `git clean -fdx` from anyone who hadn't built locally. The `Archives/`
   tier already covers historical churn; `swarm_docs/` is current shipped
   collateral, not stale state.
2. **Regenerate-in-place** — `scripts/build_swarm_docs.py` overwrites the
   same paths. Diffs are noisy (binary `.docx`) but bounded; reviewers should
   focus on the matching `.md`/`.html`/`.json` peers when judging content.
3. **Archive via Studio** — when a chapter is retired, move the file under
   `Archives/swarm_docs_<DATE>/` and record the move as a Studio evidence
   row against the originating proposal. Do **not** create loose
   `*_DEPRECATED.md` markers — that pattern is what
   STEP-STOP-MARKDOWN-TRACKER-RECREATION-20260430 already retired.

## What stays out of `swarm_docs/`

- Heartbeat trackers (`CURRENT_FOCUS.md`, `STALE_PROPOSALS.md`,
  per-agent `DISPATCHED_WORK.md`) — gated behind `SWARM_LEGACY_MD_TRACKERS`
  in `fridays/orchestrator.py`. Studio + KC carry the canonical record.
- Per-agent transcripts and session journals — stay under
  `Archives/HISTORY_V1/` or the Vortex snapshot store.
- Test/CI logs — they belong in `logs/` (gitignored) and the spine event
  feed.

## Operator workflow

```bash
# Regenerate all chapters in-place
.venv/bin/python scripts/build_swarm_docs.py

# Verify diff before commit
git --no-pager diff --stat swarm_docs/

# Archive a retired chapter
mkdir -p Archives/swarm_docs_$(date +%Y%m%d)
git mv swarm_docs/<retired>.docx Archives/swarm_docs_$(date +%Y%m%d)/
```

## Why not untrack outright

Each option was scored:

| Option            | Pros                                  | Cons                                                                 |
|-------------------|---------------------------------------|----------------------------------------------------------------------|
| Untrack + ignore  | Lean repo, no binary diffs            | New clones lose the manual until they run the builder; CI breaks     |
| Regenerate fresh  | Always-current outputs                | Builder is heavy; CI cost rises; offline operators have stale docs   |
| **Keep + archive (chosen)** | Operators get the manual on clone; archive captures retirement | Binary diffs occasionally show up — accepted cost                     |

## Linked stories

- STEP-TRACKED-SWARM-DOCS-CLEANUP (closes with this policy)
- STEP-STOP-MARKDOWN-TRACKER-RECREATION-20260430 (sibling — retired the
  loose heartbeat trackers)
- STEP-DOCS-MANUAL-RELATABLE-UX-20260430 (still open — covers in-app
  manual UX, not the source-tree policy)
