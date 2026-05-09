# Studio Change Log - 2026-05-09

This log records system changes made today so Studio has a human-readable trail
alongside Git commits, PRs, Vortex heartbeats, and TimeWizard snapshots.

## PR #13 - Vortex Git Drift and CI Stabilization

Merged commit: `2245b7a9`

Changes:

- Added remote drift checking to `/api/git/status?check_remote=1`.
- Added UI warning toast when the local workspace is behind the tracked remote.
- Fixed GitHub Actions by removing invalid Ruff `W503` usage.
- Narrowed CI to maintained watchdog/Vortex paths instead of unrelated legacy
  repo debt.
- Made `utils/sandpits.py` respect `SWARM_ROOT` so GitHub runners do not try to
  create `/home/seven`.

Validation:

- GitHub Actions run `25593478447` completed successfully.
- Local focused watchdog/Vortex tests passed.
- Secret scan passed.

## PR #14 - Grok Pot Reviewed Intake Lane

Merged commit: `1634c752`

Changes:

- Added `sandpits/studio/grok_pot/README.md`.
- Added `sandpits/studio/grok_pot/REVIEW_2026-05-09.md`.
- Reviewed remote Grok Pot branches and recorded why their current Coder Bible
  drafts should stay in intake instead of being promoted.

Reviewed branches:

- `origin/grok-pot-seed-bible`
- `origin/proposal/grok-pot-bible-seed`
- `origin/proposal/grok-pot-coder-bible-seed`

Validation:

- GitHub Actions run `25593554020` completed successfully.
- Secret scan passed.

## Operating Note

Future system changes should leave three traces:

1. Git commit or PR.
2. Vortex/TimeWizard snapshot.
3. Studio-facing note in the relevant sandpit, project folder, or Studio change
   log.
