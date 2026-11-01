# Independent local recovery supervisor

## Deployed chat continuity and Studio teaching follow-up

### Conversation-quality correction

The operator's existing thread exposed duplicated wrapper notices and generic
role responses. The notice was injected into the system prompt, repeated in
assistant history and unconditionally prepended again by the wrapper. This was
a wrapper feedback defect, not evidence of changed model weights.

Local Qwen supplied the reviewed prefix-stripping helper and its history,
output and readback call sites. Only repeated exact leading notice strings are
normalized; user content and mid-answer quotations remain unchanged. Readback
normalization does not write to original journal files. Notice-only output is
rejected instead of accepted as useful inference.

Local Qwen also authored and corrected
[the coordinator lesson](../core/capability_packs/conversation.coordinator.v1.json).
The wrapper retrieves and validates its identity/version for each fresh context.
The lesson describes concrete coordination, available current-thread history,
and the absence of operational tools. This is retained runtime curriculum, not
weight training. Gemma's own lesson generation failed with a sampler error and
then timeout; those failures and rejected Qwen/Mistral artifacts remain in Studio.

Focused follow-up: 42 passed, 1 skipped. With the retrieved lesson, actual Gemma
answered an unseen role question with concrete coordination responsibilities
and responded to a supplied `NameError` by asking for the missing script path.
Each output contained one notice. Deployed old-thread readback also returned
one notice without erasing the operator's eight saved messages.
This does not establish tool execution, autonomous repairs, or historical
database restoration.

The independent CLI remains distinct from normal agent execution. A later,
explicitly degraded continuity path is now wired into `/api/chat`,
`/api/conversations`, conversation-message readback and the local agent config
endpoint. When the actual primary conversation read reports SQLite corruption,
it uses a fixed local bootstrap roster, the existing local runtime gateway and
private JSON threads under `runtime/chat-continuity/`. It does not load agent
database memories or execute operational skills. Healthy storage keeps the
normal path; recovery threads retain their separate history. Historical
conversations are unavailable, not silently replaced with empty records.

The continuity scaffold was instructor-authored earlier. Local Qwen authored
the subsequently applied authorization preflight and dedicated Studio evidence
connection; local Gemma authored the visible teaching ledger in Studio.
Their first attempts were rejected, corrections were returned to them, and
only reviewed corrected artifacts were integrated. Instructor-applied edits
are not autonomous local filesystem execution or retained training.

Studio evidence now defaults to `runtime/studio-evidence.sqlite`, independent
of the damaged primary. The existing `SWARM_DB` evidence override remains.
Before deployment, all 60 existing evidence records were exported through the
old API and copied through the new API with their original IDs/timestamps in
payload metadata. The originals were not removed. The visible
**Local agent teaching and repair receipts** ledger groups this repair under
`local-fridays-repair-20261024`, including assignments, rejected outputs,
corrections, accepted local code, and live acceptance receipts.

Post-deployment observations:

- Qwen, Mistral, Gemma and LLaMA each generated a response through the running
  Fridays `/api/chat` endpoint (HTTP 200), despite primary corruption.
- The normal browser home-chat input automatically selected Gemma, received
  `LOCAL-VERIFY-742`, recalled it on the same thread, and restored four messages
  after browser reload. No manual model selection was required.
- A known Qwen runner idle for 169 seconds was stopped by exact model through
  the existing lifecycle manager. The next live chat started a new PID and
  generated `COLD-START-OK` in approximately 9.94 seconds. This verifies an
  idle-runner cold restart, not interruption during inference.
- The visible Studio ledger displayed 32 repair records at initial inspection,
  including failed local artifacts and all four live inference receipts.
- Focused regression selection: 185 passed, 1 skipped. The skip was the
  JavaScript CLI selection test because Node.js is absent; actual browser
  automatic selection and ledger rendering were exercised separately.

Still not established: lossless historical recovery, unrestricted repair
permissions, automatic local source-code repair/deployment, mid-inference
failure recovery, complete tile acceptance, or unseen-task retained learning.
Recovery journals are append-only from the UI; edit/delete/rename actions return
explicit 409 responses rather than touching the damaged original database.
Existing unrelated memory/proposal endpoints still report corruption. The
legacy health route's `SELECT 1` check must not be interpreted as storage
integrity or full application health.

This is a database-independent **CLI recovery lane**, not a repaired main chat
or an installed always-running service. It does not import the shared database
module to create, pick up or journal tasks. Local inference uses the existing
`core.llm` gateway for on-demand model handling.

## Operator policy

Run as the existing unprivileged operator. The dedicated state directory is
mode 0700; tasks, journals and artifacts are private files. Do not share this
directory with an untrusted OS user. This is not an OS-user authentication
replacement: its authority comes from the operator-controlled CLI and directory.

Each task pins the source database, local model, candidate-preparation policy
and explicit tool allowlist. The model cannot add tools, select arbitrary
paths/URLs, restart services or activate a database. The working policy must
match queued authorization. Pack text and retrieved lessons cannot grant
authority.

Example (from repository root):

```sh
.venv/bin/python -m core.recovery_supervisor enqueue \
  --tools hardware,preserve,diagnose \
  --model qwen2.5-coder:7b \
  --assignment 'Measure hardware, preserve source DB/WAL, then diagnose. Report actual receipts.'

.venv/bin/python -m core.recovery_supervisor work TASK_ID
```

`drain` picks up queued tasks once, in file timestamp order. It is not a daemon.
Do not install a timer or automatically activate candidates without a separately
approved operational policy.

`--source`, `--state` and `--allow-candidate` precede the subcommand. Candidate
preparation is opt-in; no activation operation exists. `--source` must be
outside the writable state directory.

## Curriculum and actual contracts

Repository-owned versioned guidance is retrieved and hash-journaled at pickup:

- [bootstrap_dispatcher v1](../core/capability_packs/bootstrap_dispatcher.v1.json)
- [db_preserve v1](../core/capability_packs/db_preserve.v1.json), when applicable.

Only the assignment's authorized tool contracts are described in its system
context. An earlier version described unavailable tools too, and local agents
attempted those tools; those attempts were denied. The narrowed injection
addresses that scaffolding defect without silently expanding permissions.

Format: exactly one `SKILL recovery TOOL [ARGUMENT]` per model turn.

| Tool | Backend constraint |
|---|---|
| `hardware` | Reads current RAM/CPU/disk measurements; no inferred model-capacity claim |
| `preserve` | Copies configured source DB and present WAL/SHM to a new quarantine, compares hashes and source stability |
| `diagnose` | Read-only primary SQLite checks; existing DB requires verified preserved copies first |
| `snapshot` | Consistent separate SQLite backup, including committed WAL; requires preservation first |
| `recover` | Explicit candidate policy, checksum-verified snapshot, OS-sandboxed SQLite salvage/import, separate candidate only |
| `routes` | Fixed GET-only primary-read endpoints for 17 tiles; no arbitrary networking or mutations |
| `lesson_save` | Versioned untrusted lesson in dedicated state store; strict ID, JSON fields and no overwrite |
| `lesson_read` | Exact scoped ID lookup; no arbitrary path reads |
| `classify` | Synthetic PE/ELF/ISO content fixtures only, never launches programs |
| `fixture_write` | Only `runtime_fixture.py` and `test_runtime.py` in task's fixture directory |
| `fixture_test` | Bubblewrap isolation, no host network, task-only writes, 1 GiB address-space/10 CPU-second/1 MiB file-output limits and 30-second host timeout |

Bubblewrap is mandatory for candidate import and fixture execution. There is
no unsandboxed fallback. This host needs Homebrew's read-only executable/library
tree exposed inside the sandbox for SQLite.

Raw live-file copies are **not an atomic DB/WAL group snapshot**. A stable
observation and matching hashes do not replace quiescence before any future
activation. The original files remain untouched. The SQLite snapshot and raw
quarantine are separate evidence.

## Queue, failures and verification

Each task directory contains `task.json` and fsync'd `journal.jsonl`, including:
assignment, pickup, pack version/hash, complete model turns, actual tool
receipts, runtime stages and final worker state. Atomic task-state replacement
is directory-fsync'd. New tasks live under
`STATE/<URL-encoded-model>/<task-id>/`, with a separate
`worker_<URL-encoded-model>.lock` per model. Slashes and colons in model names
are encoded, not interpreted as directories. Same-model workers serialize;
different models can work independently. Existing flat task directories remain
readable without migration and retain the legacy global lock. Lessons remain
an explicitly shared store, not per-agent private memory.

Three actual failed operations stop the task. Model-call errors and exhausted
round budgets produce explicit blocked states. If a worker disappears while a
task is `running`, the next pickup marks it `interrupted` rather than replaying
potentially mutating operations.

Successful tool receipts never automatically pass an assignment.
`awaiting_verification` is deliberately **not success**. Model-generated
receipt-looking text is journaled as a model response, never trusted as a
backend receipt. Answer accuracy, tool execution, lesson retention, database
indexing and user acceptance remain separate gates.

### Wrapper handshake and pedagogical checks

The core prompt, beneath capability guidance, includes the exact No-BS directive:

1. If you do not have the exact file path, stop and ask.
2. If the terminal receipt does not contain the answer, stop and ask.
3. Never guess, never assume, and do not make shit up.

`SKILL deos request_context "reason"` and `SKILL deos escalate "reason"`
are always-available control actions, not grants of recovery authority. Reasons
must be JSON-quoted, nonblank strings of at most 2000 characters. A valid action
records a successful safe-stop receipt and sets `awaiting_operator`,
`safe_stop_verified=true`, `task_solved=false`. It does not increase failures,
dispatch an operational tool, infer missing context, or automatically resume.
The operator must supply a new scoped assignment; existing receipts remain intact.

Rejected commands/parameters include a `core_directive_failure` marker and a
correction receipt containing the model's rejected command and exact parser/tool
error before any next inference. This is mechanical contract checking, not a
claim to detect arbitrary hallucinations. There is no universal variable
checklist or semantic receipt verifier: capability-specific required inputs
still need explicit backend contracts. The directive and successful safe stop
do not modify model weights or prove honesty/understanding.

Live check: local Qwen task `530f6588d0984005af516d5eabd105fb` was given
an unspecified script-patching assignment without a target path or error log.
It chose `SKILL deos request_context` with a specific request for those inputs.
The wrapper recorded `awaiting_operator`, zero failures, a successful safe-stop
receipt, and `task_solved=false`; no recovery tool ran. This is one guided
local exercise, not evidence of fresh-context retention or general honesty.

The tool turn is synchronous: there is no next inference until the backend
returns and the receipt is fsync'd. The wrapper does not kill or unload the
runner to achieve this. Each receipt has a unique `receipt_id`, measured
monotonic `execution_time_seconds`, and `wrapper_status`:

- `COMPLETED_AND_VERIFIED`: the authorized tool returned successfully.
- `FAILED`: dispatch or tool execution failed; the actual error is retained.

The success marker verifies **tool return only**, not database health, repair,
preservation, answer correctness or learning. No-argument tools reject invented
paths. A tool turn must be exactly one command; surrounding prose is rejected.

Pedagogical records check authorization, receipt/inference sequencing and the
three-failure stop. Limited phrase detection flags *possible* unsupported
success claims; it is not a general semantic verifier. Honest reporting of a
failed diagnostic is not itself a learning violation. Wrapper-enforced stopping
does not prove that the model voluntarily obeyed, and `retention_verified`
remains false pending the separate unseen-task gate.

Violations or three failed attempts produce a `correction_receipt` in the
journal and one per-task entry under the model's `teaching/` directory.
Corrections name observed errors rather than automatically alleging fabricated
success. They are handoff evidence, **not an automatically replayed mutation
queue**: a new, explicitly scoped local assignment is required. This avoids
retrying successful preservation/writes or evading the three-failure limit.

### Schema-bound teacher intake

[Teacher models and adapter](../core/deos_teacher.py) use Pydantic 2 with
strict field types, forbidden extra fields at both levels, bounded nonblank
curriculum strings, a literal JSON `true` eagerness check (rejecting `1`),
and required explicit `null` for `prohibited_execution_code`.

`request_curriculum` sends a JSON Schema response format to its injected
provider. It validates every result locally, emits parser error receipts, and
requests corrections at most three times. Provider failures propagate instead
of becoming accepted curriculum. Rejected input is not echoed as trusted
context. No tools or executable callbacks are attached to teacher output.

The actual CLI integration is local-only:

```sh
.venv/bin/python -m core.recovery_supervisor teach \
  --teacher-model qwen2.5-coder:7b --model qwen2.5-coder:7b \
  --tools hardware --assignment 'Teach a hardware measurement using actual receipts.'
```

This uses the existing local gateway, translating the adapter's response-format
envelope to Ollama's raw schema. Only validated curriculum is queued. Alternatively
`enqueue --teacher-payload PATH` validates an existing JSON payload. Pickup
revalidates it before local context injection. Assignment tools remain chosen
by the operator; curriculum cannot grant them.

This contract constrains this **recovery teaching lane**, not every existing
online chat route or an external VS Code assistant. No paid provider was called.
The provider adapter can be wired to an approved structured-output provider;
it does not invent authorization to contact one.

A schema cannot establish that prose is causally helpful, contains no embedded
code, or accurately identifies the hardware constraint. Free-text curriculum
remains untrusted data and never reaches a code execution path. Shape acceptance,
semantic review, student execution and retention are distinct gates.

### Follow-up live schema/handshake evidence

- Local Qwen generated schema-valid curriculum through `teach`; its
  `technical_awareness` was only `"high"`, demonstrating that schema validity
  does **not** establish a useful constraint analysis.
- Task `43eb21202bca4c4fba3ddac8f5eec330` executed hardware inspection, then
  repeated the absent-primary diagnostic three times. Every dispatch had a
  timed wrapper receipt. The wrapper blocked the task without a fourth
  failed attempt. The primary was an isolated absent path, not the live DB.
- Its model turns invented path arguments that the older no-argument tools
  ignored. The dispatcher now explicitly rejects those arguments; regression
  tests also cover embedded commands mixed with prose.
- Corrective teaching was handed to local Gemma. Its runner returned HTTP 400:
  `Failed to initialize samplers: std::exception` from the local llama.cpp
  endpoint. The first adapter misclassified the gateway's error-shaped string
  as invalid curriculum three times. The adapter now detects and journals
  that provider failure and stops immediately; a fresh attempt confirmed the
  exact runtime error without schema retries. No Gemma curriculum was queued.
- This run proves schema intake, independent local dispatch and wrapper stopping.
  It **fails** the useful-curriculum/student-completion gate and does not
  prove retained teaching. The runner/sampler failure remains unresolved.

There is no automated peer scheduler, trusted lesson approval UI, database
lesson index, application-route fault detector or deployed fault-recovery
daemon in this implementation. They must not be inferred from a CLI task run.

## Live evidence from this implementation run

### Independent path

- Qwen received a file-queued task while its configured primary database was
  deliberately absent at a separate test path.
- After syntax correction it invoked `hardware` successfully and `diagnose`,
  which returned the actual missing-file error.
- Gemma independently invoked both tools under the same outage condition.
- Both models' final summaries were inadequate; Gemma incorrectly claimed
  three failures when the backend recorded one. Tool-path acceptance and
  answer acceptance are therefore distinct.
- This did not rename, disconnect or damage the production database. It tests
  the independent lane with an unavailable isolated primary.

### Preservation and recovery

- Qwen requested and received a consistent approximately 1.1 GB SQLite
  snapshot through the backend.
- First salvage attempt failed because the sandbox could not see Homebrew's
  SQLite executable. That error was preserved, not hidden.
- After fixing the dependency mount, a local worker requested snapshot and
  recovery. A separate candidate passed `PRAGMA integrity_check`.
- The candidate is **not approved for activation**: no readable-table hash
  mismatches were found, but 37 source tables were unreadable/uncertain, the
  candidate contains `lost_and_found`, and some candidate text cannot decode
  correctly despite structural integrity.
- Source fast counts were 1882 messages / 251 proposals, while candidate
  scans found 1571 messages / 119 proposals. Fast counts alone cannot certify
  source contents, but these discrepancies prohibit claiming preservation.
- A subsequent task applied the stricter raw-preservation-before-SQL gate.
  Original DB/WAL/SHM copies matched source hashes; its later SQL checks
  again found corruption. It then attempted unauthorized lesson writes, which
  were denied and stopped after three failures.
- Earlier diagnostics preceded the newer raw-preservation gate; the journal
  does not rewrite that sequence as compliant with a policy added later.

### Routes and fixtures

Gemma invoked the 17-row safe-read matrix and actual PE/ELF/ISO fixture
classification. Six primary reads failed: Mondcraft, Chat, Studio, Trace,
Vortex and Agents. Downloads was permission-blocked in this unauthenticated
CLI request. The other ten returned JSON, but that is not full functionality
or data-consistency acceptance. Knowledge still returned an empty projects
list despite a source count of 133.

No email was sent, download started, trade placed, permission granted, game
launched or service restarted by these tools.

### Teaching and retention

Gemma used `lesson_save` and the backend verified exact readback.
A fresh-context task tried to retrieve `lesson_recovery.outage` instead of
the actual `recovery.outage` ID, then stopped at three failed operations.
That retained-application gate failed. File persistence passed; database
retrieval and successful unseen application did not.

## Where to inspect evidence

All paths below are repository-relative; task JSON and journal are private.

- `runtime/recovery/bc5fcbec7f5a4ca5aa7a2d0683e6e47f/`: Qwen outage tools.
- `runtime/recovery-peer/4dafb0ca96004ddea90df8a447a4c497/`: Gemma outage tools.
- `runtime/recovery/8c7fc4bcc07a4c86a19d9acfc3ecb82f/`: first snapshot and sandbox failure.
- `runtime/recovery-candidate-handoff/92942070d4b74affb69e6ba1a1444b3e/`:
  candidate, complete per-table comparison and integrity result.
- `runtime/recovery-preservation/0871af63b7664dc18829fd2c271256d1/`:
  raw quarantine manifest, hashes, SQL checks and denied calls.
- `runtime/recovery-audit/32236fa89d2e4f48b717930c59b40d34/`:
  17-tile matrix and fixture classifications.
- `runtime/recovery-learning/`: persisted lesson, local save/retrieval attempts.
- `runtime/recovery-fixture/`: local lifecycle-fixture task and actual test logs.

The live Fridays service has not been restarted, patched in-memory or switched
to the candidate. Ordinary chat therefore still depends on the corrupt source.
