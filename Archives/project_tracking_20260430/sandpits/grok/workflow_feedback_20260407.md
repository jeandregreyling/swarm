# Workflow Feedback — Dynamic Textarea Test [2026-04-07]

## What worked
- You DID emit real SKILL commands (no hallucination) ✓
- You created proposal INTERNAL-ELEVEN-0503 correctly ✓
- fs_patch on chat.css executed and patched the file ✓

## Issue: Proposal sequence ordering
You executed `fs_patch` BEFORE calling `alm_self_approve`. The correct sequence is:

1. `SKILL alm_create_proposal` — raise the proposal first
2. `SKILL alm_vortex before-<label>` — set save point BEFORE touching files
3. `SKILL alm_self_approve <proposal_id>` — move to IN PROGRESS
4. `SKILL fs_patch` / `SKILL fs_write` — THEN make changes
5. `SKILL fs_readonly ... lines ...` — verify
6. `SKILL alm_complete <proposal_id>` — mark done for Ghost

You also accidentally created a second malformed proposal (INTERNAL-ELEVEN-0504) where
the fs_patch SKILL output was used as the proposal title. This happens when you call
`alm_create_proposal` after executing a SKILL and pass the output to it.

## Guidance for next time
- Call alm_create_proposal FIRST, with a clean short title and description (not SKILL output)
- Note the proposal_id returned, use it for alm_self_approve and alm_complete
- Make file changes ONLY after self-approving
- The system will handle vortex checkpoints automatically on self-approve

The feature you worked on (auto-grow textarea + send glow) is now marked DONE and 
awaiting Ghost review. Good work on the actual SKILL execution.
