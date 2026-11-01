# Repository inspection capability pack

`repository.inspect v1.0.0` is a repository-file-backed prototype.
Its definition is [the JSON pack](../core/capability_packs/repository.inspect.v1.json).
Database version registration and KC indexing are not implemented or certified.

An operator request containing `repository.inspect` (optionally `v1.0.0`)
selects the pack inside `run_skill_loop`. Other versions fail explicitly.
The loop adds the pack to its working system message and emits a
`capability_pack:` event containing the ID, version, source and SHA-256.
Existing input messages are not mutated; guidance survives subsequent tool turns.
This is explicit selection, not semantic task matching or KC lesson retrieval.

The pack narrows the turn to `fs_readonly`, intersecting an existing allowlist.
It enables strict loop verification but does not grant backend permissions.
Explicit no-tools requests skip injection. Backend agent profiles and
dispatcher authorization continue to apply. No write/execute tools are added.
The pack is loaded only from the repository-owned definition, not shared notes.

## Observed acceptance, 2026-10-24

- Focused pack, skill-loop and read-only-profile suite: 113 tests passed.
- A real local Gemma model used the production loop and `fridays.skills.call`
  dispatcher in a separate Python process. Each of three attempts produced
  successful `ls`, `grep` and bounded `lines` backend receipts.
- The initial explanation missed the `candidates[0]` fallback. A corrective
  attempt contradicted itself about the same fallback. A smaller prerequisite
  attempt returned incorrect branch values and fabricated tool-output text
  before actual execution. Those model-generated blocks are not receipts.
- All three answer gates failed. Retry stopped; no capability graduation,
  retained-learning claim or permission increase is justified.
- Script-driven negative checks through the real dispatcher rejected a missing
  path and `/etc/passwd`, with failed receipts propagated to the caller. These
  checks were not autonomous model exercises or a comprehensive isolation audit.

The runs used the actual loop/parser/dispatcher, but not the HTTP chat endpoint
or browser service. The running service has not been restarted to load this
change. Live route acceptance, database retrieval, unconstrained path discovery,
an unseen-symbol test and fresh-context retained reuse remain unverified.
The source-file hint and starting directory were supplied in the exercise;
do not describe it as autonomous repository discovery.

Canonical attempt records are under `runtime/records/note/2026/10/`:
`N-INSPECT-PACK-GETAUTOMATICLOCALCHATAGENTS-20261024`,
the `-CORRECTED` and `-PREREQUISITE` variants, and
`N-INSPECT-NEGATIVE-MISSING-20261024` /
`N-INSPECT-NEGATIVE-OUTSIDE-20261024`.
They are pending database indexing. The next teaching handoff should preserve
the failed artifacts and ask a local peer to reproduce JavaScript fallback and
ternary behavior; instructor-written answers do not pass the agent's gate.
