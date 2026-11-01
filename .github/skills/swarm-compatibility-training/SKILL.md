---
name: swarm-compatibility-training
description: 'Teach local Gemma and Qwen bounded tool calling, diagnostic feedback, repair memory, and Wine/Proton compatibility-workbench reasoning. Use when asked to train local agents for application repair, RDR2 diagnostics, or an agent-computer interface.'
---

# Local compatibility-workbench training

Created: 2026-10-24 11:32:47 Australia/Melbourne (operator request timestamp).

## Goal

Teach local agents through their existing wrapper, actual tool receipts,
targeted feedback and unseen retests. Do not replace local work with an
instructor-written orchestration fix.

## Curriculum

Read [the schema-compatible teacher payload](../../../core/capability_packs/compatibility.workbench.v1.json).
Its prerequisite and procedure fields define the assignment, authorized command
formats, exercises, acceptance requirements and failure boundaries.

This is a DEOSTeacherPayload, not a recovery bootstrap-pack entry. The existing
recovery supervisor has a fixed bootstrap-pack list; do not add this ID to that
list or assume directory discovery loads it. Deliver it through the existing
validated teacher-payload intake when authorized. Inspect that intake before
use. Loading this editor skill does not deliver it to local inference agents.

## Procedure

1. Inspect the effective wrapper permissions and teaching-intake contract.
2. Validate the payload with the existing teacher validator.
3. Use the authorized assignment workflow to deliver the curriculum without
   granting additional tools or silently switching model identities.
4. Require pickup acknowledgement and one harmless real dispatcher receipt.
5. Run the curriculum's teach-back and unseen exercises; give focused correction
   only after an observed failed attempt.
6. Record and read back evidence through an authorized durable store.
7. Report prepared, accepted, picked-up, attempted and verified separately.
   If delivery is unavailable, report prepared but not delivered.

## Boundaries

- Instruction-based training is not LoRA or a model-weight update.
- Never launch a game merely to demonstrate that this skill was loaded.
- Never claim training success from a stored payload or an untested answer.
- Preserve existing approval gates and unrelated worktree changes.
- Do not write repair history into the README.
