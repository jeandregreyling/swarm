# Grok-Pot-Money-Maker (P-855E64250C)
**Status:** Active | **Owner:** Seven | **Methodology:** Mixed

## Change Log (Plain English - What, When, Why)
**May 9, 2026 - Studio & Git UX Focus (Top Priority)**
- Logged user feedback: No visible changes in DEV 5051 despite branch pull, no Blackboard, no easy branch selector or git buttons in Studio/Git UI.
- Shifted priority: Studio + Git integration is now #1 (branch preview, pull/checkout buttons, ENV awareness, Blackboard visibility, one-click operations).
- Paused Money Bot / Newsletter / revenue features until Studio is solid.
- **Why:** Make the multi-layered flow usable without terminal commands so changes actually show in DEV/UAT before landing in Fridays.

**May 10, 2026 - Step 4 Complete: Studio Projects Git Branch Bar**
- Added `/api/git/branches` and `/api/git/checkout` so Studio can list local branches and switch an environment worktree through an ALM-gated mutation.
- Added a Projects-panel Git bar for DEV: branch/status badge, branch selector, Checkout button, full Git-panel shortcut, and refresh-backed status loading.
- Checkout is intentionally conservative: it only targets existing local branches and refuses to run when the DEV worktree has uncommitted changes.
- Tests added: `tests/test_studio_projects_git_branch.py` covers branch listing, dirty-tree checkout blocking, and the Projects UI contract.
- Validation: `pytest -q tests/test_studio_projects_git_branch.py`, `node --check frontend/static/js/views/projects.js`, and `python3 -m py_compile frontend/blueprints/git.py tests/test_studio_projects_git_branch.py` all pass.
- **Why:** Seven can now see and change the DEV branch from Studio Projects without dropping to terminal commands, while keeping checkout behind ALM and dirty-tree safety checks.

**May 10, 2026 - Step 5 Complete: Blackboard Visible in Project Tile**
- Added `blackboard_count` to `core.knowledge.projects.list_projects()` so the list endpoint carries active Blackboard note counts without N+1 detail calls.
- Updated Studio project rows to show the count in metadata and an accent line when a project has active Blackboard notes.
- Tests updated: `tests/test_projects.py` asserts the aggregate, and `tests/test_studio_projects_git_branch.py` asserts the UI contract remains present.
- Validation: `pytest -q tests/test_studio_projects_git_branch.py tests/test_projects.py`, `node --check frontend/static/js/views/projects.js`, and `python3 -m py_compile core/knowledge/projects.py tests/test_projects.py tests/test_studio_projects_git_branch.py` all pass.
- **Why:** The next agent/operator can see handoff-note presence from the project list instead of opening each project cold.

## Sub-Tasks (Updated)
1. [x] Initial Money Bot building block (tested)
2. [x] Full Money Bot + Newsletter formatter (parked)
3. [x] Log all current bugs in PROJECT_PLAN.md
4. [x] Add branch selector + git buttons in Studio UI (DEV 5051)
5. [x] Make Blackboard visible in project tile
6. [ ] Make DEV default to feature branches and show commit status
7. [ ] Clean up stuck proposals in Git ALM

## Blackboard Notes
- User wants Git operations as UI buttons, not terminal commands.
- Projects should span ENVs and show 'Built in DEV' status.
- All conversation between us is now logged here as steps.

Pull this branch and refresh http://localhost:5051/ui to see updated plan. Focus locked on making Studio/Git usable first.
