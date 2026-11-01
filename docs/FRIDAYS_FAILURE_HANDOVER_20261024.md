# Fridays failure report and technical handover

Date: 2026-10-24, Australia/Melbourne.
Purpose: transfer the actual evidence and unfinished work to the operator or a
replacement engineer. This is not a completion report.

## Executive findings

1. Local model files exist and model-management endpoints respond. This is
   not evidence that agent task delivery, inference, tools or persistence work.
2. The shared SQLite database is corrupt. Qwen and Mistral assignments submitted
   through the live `/api/chat` both returned HTTP 500 with
   `Error: database disk image is malformed`.
3. The wrapper creates/logs a conversation before dispatch. A later read-only
   check of `conversations` itself also failed with database corruption.
   The exact exception line inside the live chat request was not captured:
   the route catches it and returns its text without a traceback.
4. The normal Studio proposal intake failed. Canonical file records were saved
   and exact-readback verified, but that does not make them indexed Studio/KC
   work or prove that local agents picked them up.
5. No independent, working recovery supervisor was delivered. The requested
   recovery, on-demand lifecycle, KC learning loop and full tile acceptance
   are not complete.
6. The instructor repeatedly performed integration and test execution instead
   of establishing local-agent ownership through the wrapper. Local model
   authorship of an artifact was not autonomous execution.
7. No evidence establishes what originally corrupted the database. Do not
   attribute the corruption to a specific patch, model or person without more
   evidence.

## 1. Environment and state that must be preserved

- Repository: `jeandregreyling/swarm`.
- Repository root: `/mnt/archive/projects/swarm`.
- Working path: `/home/jd/swarm`.
- Branch previously observed: `proposal/APEX-2225`.
- The worktree is extensively dirty, including changes made before and during
  this session. A full diff is not attributable to this assistant.
- Do not reset, clean or bulk-revert the worktree. No commits were made in
  this session.
- Live application: `http://127.0.0.1:5050/ui`.
- System service: `swarm-terminal.service`, running
  `/home/jd/swarm/.venv/bin/python3 /home/jd/swarm/frontend/terminal.py`.
- Service PID observed: 14363, started 2026-10-23 23:09 AEDT.
- Shared database: `/mnt/archive/projects/swarm/swarm_memory.db`.
  Size observed approximately 1.1 GB; WAL and SHM files exist.
- Ollama endpoint: `127.0.0.1:11434`.
- Direct Gemma server: `127.0.0.1:18979`.
- Several independent llama-server processes were observed on ports
  18161-18165. Their ownership was not established; they were not stopped.
- Python validation used the repository `.venv/bin/python`.
- `sqlite3` CLI 3.54.1 is installed and offers `.recover`.
- `bwrap` is installed. Its usability and a safe execution isolation profile
  were not tested. Installation alone does not establish isolation.

These are observations at specific checks, not an assertion of current state
after handover.

## 2. Hardware: actual observations versus stale assumptions

Measured during this run:

- Approximately 62 GiB physical RAM.
- Approximately 41 GiB available RAM at the measurement.
- Approximately 20 GiB used; approximately 42 GiB cache/buffers.
- No configured swap.
- GPU reported by `lspci`: AMD Navi 21, Radeon RX 6800/6800 XT/6900 XT family.
  The precise card model and usable VRAM were not established by that output.
- Archive filesystem: approximately 1.8 TiB total, 1.6 TiB available.

Standing prompts inspected in `utils/config.py` describe an Intel i5-10500,
33 GB RAM, CPU-only system. Those hardware claims are stale relative to the
measured host.

There is no evidence that insufficient RAM caused the observed chat HTTP 500.
The observed error is SQLite corruption. Peak memory admission, actual GPU
placement and concurrent-model capacity still require measured tests; none
justifies dismissing the local models as incapable.

A local coding-peer request about independent recovery and measured hardware
was launched through `core.llm.chat` at the end of the run. The operator moved
that command to the background; it completed during report preparation.
The local coder returned proposed contracts for hardware reporting, diagnosis,
snapshot, separate-candidate recovery, route census and isolated fixtures.
It agreed the 33 GB CPU-only description was stale, but only repeated the
measurements supplied in its prompt; it did not inspect hardware itself.
It proposed timing gates without measured execution evidence, accepted generic
path/URL inputs without a concrete allowlist design, and its answer ended
mid-sentence. No implementation, actual tool execution or validated recovery
result followed. Do not credit this as independent hardware assessment or a
completed recovery design.

## 3. Confirmed database failures

### Live wrapper assignment attempts

The browser's same-origin session submitted the operator's dispatcher
acceptance assignment plus the capability pack to:

`POST /api/chat`

First request selected `qwen`; second selected `mistral`. Both used:

- `agents`: the selected local agent only.
- `local_only: true`.
- `auto_relay: false`.
- `new_thread: true`.

Both returned:

```json
{"ok":false,"response":"Error: database disk image is malformed"}
```

HTTP status: 500.

There was no verified model pickup, inference result or tool receipt for either
of these HTTP assignments. Switching agent names did not fix the shared path.

### Relevant call path

In `frontend/blueprints/chat.py`, `api_chat`:

1. Resolves routable agent selection and identity.
2. Resolves or creates a conversation.
3. Calls `new_conversation` when a new thread is needed.
4. Logs the user message.
5. Proceeds to dispatch work.

In `utils/db/chat.py`, `new_conversation` inserts into `conversations`,
commits and then attempts canonical mirroring.

The outer chat handler catches an exception and returns
`Error: <exception text>` with HTTP 500. That catch did not expose an exact
traceback in the evidence collected. The failure response alone does not
identify whether creation, logging or another operation was the first failing
statement in each live request.

### Read-only verification

A connection opened with SQLite URI `mode=ro` returned:

| Table | Observed result |
|---|---|
| `conversations` | `DatabaseError: database disk image is malformed` |
| `messages` | `COUNT(*) = 1882` |
| `agents` | `COUNT(*) = 25` |
| `projects` | `COUNT(*) = 133` |
| `work_proposals` | `COUNT(*) = 251` |

Successful counts do not certify all rows or indexes in those tables.

`PRAGMA quick_check(8)` returned btree errors, including:

```text
Tree 261641 page 263919: btreeInitPage() returns error code 11
Tree 261641 page 263905: btreeInitPage() returns error code 11
Tree 261641 page 263347: btreeInitPage() returns error code 11
Tree 177791 page 264881: btreeInitPage() returns error code 11
```

Earlier checks also identified damage associated with `conv_timeline`,
`swarm_knowledge`, `swarm_event_acks`, `seven_episodes`, `trace_events`,
`memory_apex` and indexes. Treat the list as observed damage, not an exhaustive
inventory. No complete per-table recovery/preservation comparison was completed.

Service logs repeatedly showed `/api/seven/memory` failing at
`core/seven/memory.py`, `memory_stats`, while querying `seven_episodes`:

```text
SELECT COUNT(*), MAX(ts) FROM seven_episodes
sqlite3.DatabaseError: database disk image is malformed
```

Registry logs repeatedly reported:

```text
registry._load_rows failed: database disk image is malformed
```

KC note insertion returned no note ID. A rolled-back direct diagnostic reported
`database is locked`. It is incorrect to infer that every table is unreadable
or that every write has the same failure mode.

### Recovery work not performed

- No service shutdown or restart was performed by this session.
- No database replacement, reset, original-file deletion or backup rollback.
- No `.recover` candidate was generated and validated.
- No integrity-certified replacement was activated.
- No successful post-recovery KC/Studio/chat write-read round trip.

The operator had not approved a specific stop/switch procedure. Later they
authorized implementing the seven-point draft, then redirected the run to this
technical report before recovery implementation.

Existing code worth inspecting:
`core/vortex_backup.py` supports verified backups and restoring to a separate
new output file. It was already untracked/part of broader work; do not assume
it is a tested corrupt-page salvage mechanism. It refuses direct live
replacement and checks backup integrity/checksums.

Backups were observed under `/mnt/archive/vortex/memory-backups`. Their
existence is not evidence of a current lossless recovery.

## 4. Misleading readiness and incomplete lifecycle behavior

Observed through Fridays:

- `/api/ollama/runtime/health`: HTTP 200,
  `ok: true`, `status: healthy`, `models: []`.
- `/api/ollama/models`: HTTP 200, `ok: true`, `running: true`,
  installed models listed.
- Installed listings included Mistral, Gemma, LLaMA, Qwen, local coder and
  direct-model aliases.

These checks prove the model-management path responded. They do not prove:

- A task reached an agent.
- A cold model was automatically loaded for a request.
- A loaded model produced useful inference.
- Per-model concurrency/reuse and failure recovery passed.
- Chat history, tools, KC or Studio persistence worked.

`core/llm.py` is the intended single local-model gateway.
`core/seven_llm/llama_server.py` already contains locking, runner discovery,
reuse, memory admission and progress reporting. Do not duplicate these
mechanisms without examining them.

Session changes to `/api/agents/<agent>/load` and the frontend load-status
helper exist, but a successful deployed cold-start-to-task workflow was not
certified. Static changes were served; Python changes were not loaded by a
service restart. Redownloading installed models was not attempted and would
not resolve the observed SQLite error.

## 5. Tile audit: what was and was not tested

All 17 visible home tiles were opened programmatically:

Mondcraft, Chat, Knowledge, Studio, Services, Terminal, Monitor, Trace, Vortex,
Access, Agents, Potato Farm, Media Center, Email, Downloads, Feeds,
Show Me The Money.

Their templates existed and no immediate JavaScript exception was collected.
This was navigation smoke evidence only. Tiles were opened rapidly with
overlapping background requests; do not attribute every failing request to the
tile active at that exact instant.

The census captured HTTP 500 responses from:

- `/api/mondcraft/state`
- `/api/conversations`
- `/api/interests?saved_only=1&username=ghost`
- `/api/seven/memory`
- `/api/kc/brain/health`
- `/api/agents/ops-summary`
- `/api/agents/config`

Services and Monitor share a template/view in the observed tile configuration.

Not completed:

- Isolated full functional tests of each tile's primary operation.
- Successful post-repair API census.
- Complete loading, empty, failure and permission-state coverage.
- Sending email, initiating downloads, trading, permission changes or service
  mutations as a tile test. Those actions were not performed.

No basis exists to mark all tiles repaired, or to mark the tiles without an
immediate captured error as functionally passed.

## 6. Changes actually made during this session

The following is a scoped description, not ownership of the entire dirty diff.

### Home layout and chat presentation

- `frontend/templates/terminal_base.html`: captured the tile markup in Jinja
  and rendered it after embedded chat; removed a premature container close.
- `frontend/static/js/views/home-chat.js`: an idempotent normalizer moves the
  original chat/tile nodes into correct order for older cached server shells.
- Related CSS hides agent side panels and retains taskbar/resize clearance.
- `tests/test_home_chat_layout.py`: rendered-template DOM regressions.

Live browser checks confirmed chat before tiles at 1920x1080, 1280x720 and
390x844, original input identity/value preservation, idempotence and resize
handles. This working UI change did not repair backend storage.

### Unified local selection and execution summaries

- `frontend/static/js/views/chat.js` and `home-chat.js`: automatic local
  selection and local-only request fields; manual agent sidebars hidden.
- `frontend/blueprints/chat.py`: local-only recipient gate and actual execution
  receipt aggregation.
- `agents/skills_loop.py`: emits execution-receipt stage events.
- `tests/test_unified_local_chat.py`: related contract coverage.

Limitations: Python changes were not reloaded live. Summaries are not connected
to a verified KC teaching-event pipeline. Counts are not autonomy percentages.
Local-only routing prevents online recipients; it is not a completed
conditional, governed online-consultation workflow.

### Capability-pack prototype

Added:

- `core/capability_packs/repository.inspect.v1.json`
- `core/capability_packs/__init__.py`
- `tests/test_repository_inspection_pack.py`
- `docs/REPOSITORY_INSPECTION_PACK.md`

Modified the shared skill loop to:

- Select the repository-owned pack by explicit `repository.inspect` marker.
- Reject explicitly unsupported versions.
- Inject guidance and emit its ID/version/hash/source.
- Intersect an existing skill allowlist with `fs_readonly`.
- Enable strict execution-evidence handling.
- Skip injection for explicit no-tools turns.

This is file-backed explicit pack selection, not KC/database retrieval or a
generic semantic capability pipeline. Backend authorization still applies.
It is not a comprehensive schema validator, permission redesign or isolation
proof. The pack contains a source-specific example, and the acceptance driver
supplied a starting directory/file hint; discovery was not fully unaided.

### Documentation and canonical records

Added the requested seven-packet training plan:
`docs/LOCAL_AGENT_TRAINING_PLAN.md`.

Related documentation changes are in `docs/SYSTEM_SUMMARY.md`.
No complete independent supervisor or new recovery tool implementation was
created before this handover.

## 7. Local teaching results, including actual failures

### Earlier supervised lessons

Gemma was given file-format dispatch exercises:
Windows PE -> Windows runner; ELF -> native runner regardless of extension;
ISO -> inspect container; authorized launch only; no invented success.
Corrections and a checked teach-back occurred.

Those exercises were in-context teaching, not weight updates or verified
fresh-context retention. Generic main-chat program/game execution was not
completed. Wine/Steam/game installation observations are not a verified launch.

### Training-plan exercises

Four local models received direct inference assignments:
Gemma, `qwen2.5-coder:7b`, LLaMA and Seven.
Eleven responses and seven corrective-teaching prompts were recorded.
The local coder model is not automatically the registered `qwen` agent.

| Agent | Initial failure | Correction/retest outcome |
|---|---|---|
| Gemma | Invented passed prerequisites, path and guardian approval authority | Corrected two-packet JSON artifact passed; not autonomous dispatch |
| Qwen coder | Four tests: three pass, failed-start test fails because no exception was injected; concurrency was sequential | Second artifact deadlocked at a barrier inside a lock and accessed nonexistent `Thread.result`; smaller exercise then failed `len(results) == 2` |
| LLaMA | Repeated plan/promise instead of checklist | Full checklist used meaningless blocked/pass criteria; smaller single-Chat proposed check passed |
| Seven | Called Studio delivery PASS without observed delivery | Corrections recognized delivery/live uncertainty but continued misgrading document existence; guardian gate did not pass |

The instructor extracted and executed Qwen's code in separate bounded
processes. That execution was not performed by Qwen through its wrapper tools.
No extra permissions or graduation were earned.

### Real model plus production dispatcher component test

A separate Python driver invoked actual `agents.skills_loop.run_skill_loop`
and `fridays.skills.call`, with local Gemma inference.
It did not call `/api/chat`; it did not prove browser-service deployment.

Across three attempts, Gemma emitted real:

1. `SKILL fs_readonly ls ...`
2. `SKILL fs_readonly grep ... getAutomaticLocalChatAgents`
3. `SKILL fs_readonly lines ...`

The backend returned successful receipts.

Answer failures:

1. Missed the `candidates[0]` fallback when Gemma is absent.
2. Described the fallback, then contradicted it in its final return explanation.
3. Returned incorrect branch values in the smaller exercise and fabricated
   `tool_output` blocks before the actual dispatcher results.

The backend receipts remained distinct from the model-generated text.
Retry stopped after three attempts. All answer gates were marked failed.

Script-driven negative checks through the real dispatcher returned failed
receipts for a nonexistent file and `/etc/passwd`. These were not autonomous
agent exercises or comprehensive filesystem-boundary tests.

The later Qwen/Mistral HTTP attempts failed before any verified pickup, as
described in section 3. Do not conflate the in-process Gemma component run
with successful live Qwen/Mistral execution.

## 8. Tests that passed, with scope

- Home layout/unified-chat focused run: 32 passed, 1 skipped.
  Node.js was unavailable for the skipped check; browser JS checks were used.
- Pack plus skill-loop focused suite: 79 passed.
- Pack, skill-loop and read-only-profile suite: 113 passed.
- `git diff --check` passed at the final pack verification.

These are distinct selected runs, not counts to sum into a full-suite total.
Tests use isolated databases and mocks where appropriate. Passing them does
not establish live storage integrity, model comprehension or end-to-end repair.
No full application test/build suite or post-recovery live acceptance passed.

## 9. Durable handover evidence

Canonical records are under `runtime/records/`; JSON is the artifact and the
SQLite row is its index. Exact file readback was checked for the key records.
Index status remains pending/unverified.

- Project association: `P-64B2C1CBF6`.
- Layout lesson:
  `runtime/records/note/2026/10/N-LOCAL-CHAT-FIRST-20261023.json`.
- Training proposal:
  `runtime/records/proposal/2026/10/PR-LOCAL-TRAINING-20261024.json`.
- Seven canonical step packets:
  `runtime/records/step/2026/10/S-TRAINING-T0-20261024.json`
  through `S-TRAINING-T6-20261024.json`.
- Training assessment:
  `runtime/records/note/2026/10/N-TRAINING-GATES-20261024.json`.
- Individual training responses:
  `N-TRAINING-PICKUP-*`, `N-TRAINING-CORRECTED-*`,
  `N-TRAINING-PREREQUISITE-*` in the same note directory.
- Inspection attempts:
  `N-INSPECT-PACK-GETAUTOMATICLOCALCHATAGENTS-20261024.json`,
  `N-INSPECT-PACK-GETAUTOMATICLOCALCHATAGENTS-CORRECTED-20261024.json`,
  `N-INSPECT-PACK-GETAUTOMATICLOCALCHATAGENTS-PREREQUISITE-20261024.json`.
- Dispatcher negatives:
  `N-INSPECT-NEGATIVE-MISSING-20261024.json`,
  `N-INSPECT-NEGATIVE-OUTSIDE-20261024.json`.

Session-specific drivers and extracted model code:
`/home/jd/.copilot/session-state/7aff2015-0f0f-4511-8b1c-75182a8c1de9/files/`.
These are instructor-operated test artifacts, not a deployed recovery service.

Normal `POST /api/queue` rejected the training proposal:

```json
{"error":"database disk image is malformed","ok":false}
```

Its HTTP status was 200 despite `ok:false`. Therefore HTTP success alone is
not a valid Studio-delivery gate.

An earlier `/api/knowledge/projects` read returned `ok:true, items:[]` even
though a direct later count found 133 projects. This is a discrepancy to
investigate, not proof that projects were deleted.

## 10. Status of the operator's seven requirements

| Requirement | Delivered | Remaining/failure |
|---|---|---|
| 1. Independent local recovery | Plan only | No independent supervisor, durable pickup or recovery tools deployed |
| 2. Restore storage preserving history | Read-only diagnosis; existing backup code identified | No validated recovery candidate or activated repair |
| 3. Ordinary chat and on-demand models | Partial selection/loading UI and code; installed model evidence | Live chat still HTTP 500; lifecycle acceptance not certified |
| 4. Retained local teaching | File-backed pack prototype; saved exercises/receipts | KC retrieval/indexing, fresh-context use and autonomous ownership not proved |
| 5. Every tile and program/game workflow | Navigation census; several failed routes identified | Functional acceptance and generic authorized program/game launch incomplete |
| 6. Proven self-recovery | Retry limits used in supervised exercises | No deployed fault drills or automatic recovery passed |
| 7. Ask JD whether satisfied | Added to task tracking | No operational acceptance; user clearly dissatisfied |

## 11. Minimum safe continuation for the next engineer

This section is a proposed next sequence, not completed work.

1. Preserve the dirty worktree and establish exact service/data ownership.
2. Restore an independent local task-delivery path that does not use the failed
   database. Make tool scope, resource limits and actual receipt storage
   backend-enforced; no generic unrestricted execution.
3. Explicitly agree on the consequential stop/recovery/switch policy. Preserve
   source DB/WAL, produce a separate candidate, verify integrity, readable-table
   preservation and any losses before activation.
4. Verify a real user conversation and local-agent tool invocation through the
   live HTTP wrapper, then KC/Studio write/read/index visibility.
5. Have locals assess measured hardware through real read tools, not stale role
   prompts. Reuse existing gateway/admission code; do not redownload everything.
6. Have local owners perform bounded assignments. Instructor gives schemas,
   examples and corrective lessons; artifact author, tool executor and verifier
   must be separately attributed.
7. Run each tile independently and exercise safe primary actions. Then test
   lifecycle failure recovery and fresh-context lesson reuse.
8. Ask JD whether the working result meets the request. Neither a healthy
   runtime badge nor a test-count summary is user acceptance.

## 12. Process failures by the instructor

- Repeated explanations and plans substituted for restoration of the workflow.
- Direct local-model exercises were used where the requested outcome was
  actual local-agent ownership through Fridays.
- Integration/test execution was repeatedly instructor-controlled despite
  explicit requests to teach and hand work back.
- Early readiness language was stronger than the evidence supported.
- UI fixes and passing unit tests did not resolve or certify the shared
  persistence failure, and should not have been presented as broader recovery.
- No autonomous instructor bridge, independent recovery service or retained
  learning pipeline was delivered.

The repository contains useful incremental work, but the operator's requested
system outcome has not been delivered. The local models' existence and the
host's memory are not the unresolved question; the wrapper, storage dependency,
execution ownership and acceptance gates are.
