# Branch Cleanup Plan (P-00221285D1)

**Goal**: Clean up noisy experiment branches so the repo is usable again.

## Branches to DELETE (dead experiments / test spikes)
- Most `codex/*` branches (e.g. codex/watchdog-*, codex/grok-pot-*, codex/fix-*, etc.)
- Most `proposal/*` branches
- Old feature spikes that were never merged

## Branches to KEEP / REVIEW
- `master` (main)
- Any branch with real merged work or active development
- Long-lived feature branches that still have value

## Action
1. Delete obvious dead `codex/*` and `proposal/*` branches.
2. Migrate any useful changes from old branches into master or a proper feature branch.
3. Keep the repo clean going forward.

This is part of making the project actually maintainable.
