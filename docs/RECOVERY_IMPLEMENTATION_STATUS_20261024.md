# Recovery implementation status — 2026-10-24

This records delivered code and actual local-agent execution, not a claim that
Fridays is repaired.

Final targeted validation: **117 passed** across recovery-supervisor,
agent-model-loading, repository-pack, skill-loop and Vortex-backup tests.
The actual bubblewrap fixture tests were executed, not skipped.
`git diff --check` also passed. A wider earlier selected run had an additional
failure in the pre-existing Seven error-summary wording expectation; that file
was not modified to conceal the failure.

## Six requested gates

| Gate | Delivered and observed | Remaining blocker |
|---|---|---|
| 1. Independent recovery | File queue, private journal, scoped dispatcher, hash-journaled packs, worker locking and interrupted-task detection. Qwen and Gemma received isolated-outage tasks and invoked real hardware/diagnostic tools without primary SQLite. | Local final reports were inaccurate; no unattended service or automatic fault detector installed. |
| 2. Storage preservation/restoration | Local-requested raw DB/WAL/SHM quarantine with matching hashes; consistent SQLite snapshot; local-requested sandboxed salvage; separate integrity-passing candidate and per-table comparison. | Preservation cannot be certified: 37 source tables uncertain, extra lost-and-found data, candidate text-decoding errors, message/proposal count discrepancies. Candidate not activated. |
| 3. Ordinary chat/lifecycle | Existing on-demand gateway reused by independent worker; backend runtime stages journaled. Isolated write/test tool now exists with network/host-write/resource restrictions. | Qwen's fixture-write JSON failed three times; no local lifecycle-fixture pass. Production chat still uses corrupt source; no live lifecycle gate passed. |
| 4. Teaching/retention | Repository-backed versioned bootstrap/preservation packs, task-only tool contracts, real saved/readback-verified lesson. | Fresh-context Gemma used the wrong lesson ID and exhausted three failures. Database-backed retrieval and correct unseen reuse did not pass. |
| 5. Every tile/program capability | Local agent invoked a 17-row safe-read matrix and real PE/ELF/ISO classification fixtures. | Six primary reads failed, Downloads permission-blocked, remaining ten only returned JSON. No full tile acceptance, native/Windows launch or game acceptance. |
| 6. Self-recovery | Tests cover primary absence, model-call failure, tool denial, malformed calls, bounded stopping, worker interruption, preserved-copy tampering and candidate loss detection. Actual OS-sandbox tests deny host writes and host-network access. | No deployed autonomous end-to-end recovery; production runner termination and post-repair user workflow not tested. |

## Attribution

- Instructor: authored/integrated the narrow bootstrap backend, tool contracts
  and tests; inspected actual results. It did not silently credit this
  infrastructure implementation to a local model.
- Local coder: supplied the initial `/proc/meminfo` measurement approach.
- Local Qwen/Gemma: chose actual recovery commands in the independent queue.
- Backend: executed those selected commands and recorded real receipts.
- Local artifact/report failures remain failures. Model-generated receipt-like
  text is not execution evidence, and no task is automatically graduated.
- A second coding-peer request via an old Gemma endpoint failed with connection
  refusal; using the existing on-demand gateway subsequently worked. No new
  model download or hardware purchase was needed.

## Preservation stop

The recovered candidate structurally passes SQLite integrity checks. That does
not prove preservation or usable text. Source fast counts reported 1882
messages and 251 proposals; candidate scans found 1571 and 119. Source scans
themselves fail partway through, so neither exact data-loss quantities nor
lossless recovery can be asserted.

Original DB/WAL/SHM, raw quarantine, SQLite snapshots, candidate, recovery SQL,
per-table validation and local journals are retained. No reset, old-backup
rollback, service restart or database activation was performed.

The operator's stop condition prohibits promoting this candidate as restored
history. Further forensic reconstruction and an explicit review of unresolved
records are needed before an activation decision. Successful normal
conversation/KC/Studio create-read tests have not happened.

## Actual local failures that informed scaffolding

- Bare tool name did not invoke a tool: corrected by concrete command syntax
  and backend malformed-command feedback.
- Initial sandbox lacked Homebrew SQLite dependencies: fixed read-only mounts.
- Models attempted unavailable tools: contracts are now injected only for
  tools authorized on the assignment.
- Models confused successful operations with failure counts: prompt now
  explicitly distinguishes `ok=false`; backend always counts independently.
- Long fixture JSON was malformed: stopped after three failures, no cloud
  substitution or invented test success.
- Saved lesson ID `recovery.outage` was requested as
  `lesson_recovery.outage`: retrieval failed explicitly; no fuzzy fallback
  concealed the failed retention gate.

## Lifecycle fixture result

Qwen selected the actual `fixture_write` tool, but all three artifacts failed
JSON parsing (`Unterminated string starting at line 1 column 24`). No fixture
file was accepted and no local-authored lifecycle test executed. The separate
infrastructure test did execute three instructor-authored isolation tests;
those do not substitute for Qwen's four required lifecycle tests.

See [the operational guide](RECOVERY_SUPERVISOR.md) for commands, boundaries
and exact task evidence locations, and
[the earlier failure handover](FRIDAYS_FAILURE_HANDOVER_20261024.md) for the
pre-implementation baseline. This new implementation supersedes that report's
statement that no independent runner code exists; it does not supersede its
finding that the live application is broken.

## User acceptance

Point 7 remains operator acceptance, not an automated checkbox. JD must be
asked whether the actual working result meets the request. It cannot pass
while ordinary chat and the storage-preservation gate remain unresolved.
