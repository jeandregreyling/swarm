# Hummingbird namespace and model-routing migration

Status: REVIEW ONLY. Register the Studio project `on_hold` and every task
`blocked`. No implementation, model loading, download, restart or rename is
authorised by registration.

Machine-readable companion:
[HUMMINGBIRD_NAMESPACE_MIGRATION.json](./HUMMINGBIRD_NAMESPACE_MIGRATION.json).
Task keys HB-01 through HB-20 below match that manifest. The manifest is an
ingestion mapping to existing Studio tables, not a new runtime API.

## 1. Operator-approved outcome

- Product, framework and wrapper name: **Hummingbird**.
- Primary orchestrator/state-manager identity: display `APEX`, canonical ID
  `apex`. A coding specialist is a model role behind APEX, not a new permission
  identity or a replacement for the operator.
- Stage the full migration, using compatibility readers/aliases before changing
  writers. Route legacy agent identity `seven` to `apex` at trusted boundaries.
  Treat legacy `fridays` routing identities similarly only where inventory
  establishes that they denote the primary agent, not a framework service.
- Preserve historical rows, message authors, existing session tokens, active
  sessions, credentials, signing keys and third-party names. No historical
  UPDATE/DELETE, token rewrite or bulk SQL string replacement.
- New product-owned namespaces use `hummingbird`; new primary-agent writes and
  authorisations use `apex`. Internal legacy namespaces remain temporarily only
  in an explicit compatibility map and tests. Historical read projections may
  show current labels without changing stored evidence or authors.
- Do not invalidate old cookies/tokens before their existing natural expiration.
  Security revocation and logout must still work. Do not extend legacy expiry.
- APEX delegates code generation/refactoring to an evaluated coding model via
  `llama-server`; an approved Ollama route is the bounded fallback. The host,
  not either LLM, owns resource admission, execution and authorisation.
- Scope includes Python, web UI, launchers/services, first-party tooling,
  desktop/mobile wrappers, tests and active documentation. Published repository
  URLs, package/store identities and installation data require explicit cutover
  decisions; do not silently break external clients to achieve zero grep hits.

## 2. Observed audit baseline

Snapshot: 2026-11-02, repository `/mnt/archive/projects/swarm`,
HEAD `ffc6308841193804b3dd698b4180f62606beaa20`, dirty worktree.
Re-run inventory before implementation; these are observations, not invariants.

| Surface | Observed evidence | Migration consequence |
|---|---|---|
| Footprint | 1,770 tracked files; 990 tracked text files match case-insensitive `fridays?`, `seven` or `swarm`, excluding lockfile/SVG/minified JS; 371 active-source files match | File counts, not occurrence counts; includes history, fixtures and intentional language. Classify before editing. |
| Web branding | `frontend/templates/terminal_base.html:6` says `Hummingbird — Seven's Swarm`; `utils/session_auth.py:104` contains old login branding | Change rendered product copy, not stored conversations. |
| Agent routing | `core/chat_continuity.py:42` fixes APEX to `gpt-oss:20b`; `apex_roster` is single-entry and there is no specialist fallback on this lane | Dynamic routing is a deliberate behaviour change, not already implemented. |
| Sessions | `frontend/services/auth.py:33`, `frontend/blueprints/chat.py:99`, `frontend/blueprints/sse.py:82`, `frontend/blueprints/login_bp.py:176` use `friday_session` | Login, session reads, approvals and SSE must migrate together. Flask UI sessions in `utils/session_auth.py` are a second mechanism. |
| Storage | `utils/db/_connection.py:23` defaults `SWARM_DB_PATH` to `swarm_memory.db`; project/step defaults include `seven` | Do not create a new empty database or rewrite existing rows when renaming the setting. |
| Imports/runtime | `fridays/`, `agents/seven/`, `core/seven_llm/`, `core/seven_runtime/`, `ops/llm_registry.yaml` | Move first-party modules in slices with temporary import shims and regression tests. |
| Process ownership | `deploy/systemd/apex-server-user.service` owns the persistent server; `core/seven_llm/llama_server.py:497` treats endpoint entries as externally managed | Existing external service must not be killed/adopted by a new pool without an approved ownership transition. |
| Packages | `pyproject.toml:6` names distribution `swarm`; Android uses `com.swarm.hive`; desktop uses `com.swarm.seven.desktop` | Distribution and signed application identifiers are upgrade/data contracts, not simple UI labels. |
| Studio | `projects`, `project_steps`, `project_step_deps`, `project_docs`, `project_blackboard_notes` already exist | Use these schemas; no schema migration needed to register this plan. |
| Studio gate | `core/knowledge/projects.py:580` selects todo steps without filtering project status | Project `on_hold` alone is not a proven execution barrier. Register steps `blocked`, owner `apex`, and require explicit release. |
| Studio retrieval | Prior project `P-26C093E7E6`, conversation 2828, evidence 94/95; APEX lacks an attached evidence-ID lookup | Complete structured retrieval and fresh-turn acceptance before complex refactoring. Instructor API access is not APEX tool access. |

The local model endpoint reports `gpt-oss:20B`, 8,192 runtime context and about
13.78 GB model metadata size. This is not a measured total VRAM allocation.
The installed server is build 11836 / commit `f5027fb21`; Ollama reports
0.40.6. A point-in-time AMD sample reported 17,163,091,968 total VRAM bytes and
1,204,563,968 used bytes; usage can change and this does not prove a model is
fully GPU-resident. Host MemTotal was 65,759,840 KiB, MemAvailable
46,405,460 KiB; no swap was configured. Ollama's resident-model list was empty.

Already listed local candidates include `qwen2.5-coder:7b` Q4_K_M (~4.68 GB
file), `qwen2.5:7b-instruct`, `qwen2.5:14b-instruct`, `llama3.2:latest`,
`mistral-small:24b` and `fred-cpu:24b`. Aliases and names are not proof of
capability, license, checksum, CPU-only execution or RAM footprint. Inspect the
registered blob/model card and benchmark before selecting. No new download is
required merely to start evaluation.

## 3. APEX operating contract

Goal: execute the ordered tasks below with real dispatcher receipts and narrow,
reviewed changes. Prerequisites: project released by the operator, predecessor
verified, effective tools discovered, workspace baseline preserved, and all
task-specific approvals present.

**Authorized SKILL Commands:** none on the normal APEX chat lane. Existing
structured tools include `git_status`, `grep_repo`, `read_file`, `get_diff`,
`studio_resume` and gated file/patch proposals. They do not imply arbitrary
shell, database, test-runner or service access. Bash blocks below are exact
commands for an approved bounded command runner; if no such tool is attached,
APEX must request that capability and report blocked. Do not impersonate a
tool by putting shell text into a chat response.

Every attempt records task key, agent/model/backend/quantisation, approval ID,
input scope, actual tool receipts, changed files, focused tests and outcomes,
resource peaks, rollback, uncertainty and next action in Studio. Store outputs
as evidence, not private reasoning. Reopen evidence from a fresh turn before
marking `done`; process exit, model prose and a saved task do not suffice.
`partial` is not `done`; failure stays `blocked` with its exact receipt.

The instructor can inspect and verify, but does not implement the application
rename. Specialists propose patches; only the approved host executor applies
them. No model can grant itself tools or advance its own approval gate.

## 4. Search patterns and exact command catalogue

Run from the verified root. Tracked content only for broad searches; do not scan
credentials, model blobs, databases, private sandpits or runtime history.
Use bounded per-file reads after each inventory. These patterns are classifiers,
**not replacement expressions**. Never run `sed -i`, global replace, `eval`,
history rewriting or a database-wide `REPLACE`.

| Key | Pattern (engine) | Meaning |
|---|---|---|
| RX-01 | `fridays?|seven|swarm` (`git grep -E -i`) | Broad substring inventory; catches identifiers as well as ordinary words. |
| RX-02 | `(^|[^[:alnum:]_])(fridays?|seven|swarm)([^[:alnum:]_]|$)` (`git grep -E -i`) | Standalone names; does not cover every camelCase/underscore identifier. |
| RX-03 | `\b(?:SWARM|SEVEN|FRIDAYS?)_[A-Z0-9_]+\b` (`rg`, case-sensitive) | Product-owned environment/settings candidates. Third-party variables stay unchanged. |
| RX-04 | `(?i)(?:friday_session|seven[-_:]|fridays[-_:]|swarm[-_:]|com\.swarm)` (`rg`) | Cookies, aliases and externally visible contracts. |
| RX-05 | `(^|/)(fridays?|seven|swarm)([._/-]|$)` (`grep -E -i`) | Legacy path components; separately inventory embedded names. |

### C01: root and dirty-tree baseline (read-only)

```bash
cd /mnt/archive/projects/swarm
git rev-parse --show-toplevel
git rev-parse HEAD
git --no-pager status --short
git --no-pager diff --stat
git --no-pager diff --check
```

Do not stash, checkout, clean, reset, commit or copy the existing dirty worktree
without approval. Preserve exact pre-existing edits in any file touched.

### C02: tracked inventory (read-only)

```bash
cd /mnt/archive/projects/swarm
git ls-files | wc -l
git grep -I -i -l -E 'fridays?|seven|swarm' -- . ':!requirements-lock.txt' ':!*.svg' ':!*.min.js' | wc -l
git grep -I -i -l -E 'fridays?|seven|swarm' -- frontend core fridays agents utils lib config.py pyproject.toml | wc -l
git grep -I -i -l -E 'fridays?|seven|swarm' -- . ':!requirements-lock.txt' ':!*.svg' ':!*.min.js' | cut -d/ -f1 | sort | uniq -c | sort -nr
git ls-files | grep -Ei '(^|/)(fridays?|seven|swarm)([._/-]|$)'
git grep -n -I -i -E '(^|[^[:alnum:]_])(fridays?|seven|swarm)([^[:alnum:]_]|$)' -- pyproject.toml config.py frontend/templates/terminal_base.html
```

`git grep`/`grep` exit 1 means no matches, not a parser error; exit 2 or more
is a failure. A pipeline count alone cannot prove all sources were read.
Record each command's actual status; do not hide errors with `|| true`.

### C03: identifier and contract inspection (read-only)

```bash
cd /mnt/archive/projects/swarm
git grep -n -I -E 'friday_session|set_cookie|delete_cookie' -- frontend/services/auth.py frontend/blueprints/login_bp.py frontend/blueprints/chat.py frontend/blueprints/sse.py
git grep -n -I -E 'SWARM_DB_PATH|swarm_memory\.db|DEFAULT_OWNER|APEX_AGENT' -- utils/db/_connection.py core/knowledge/projects.py core/chat_continuity.py
git grep -n -I -E 'com\.swarm|applicationId|namespace|identifier' -- android/hive-agent/app/build.gradle.kts android/seven-app/app/build.gradle.kts desktop/tauri.conf.json desktop/src-tauri/tauri.conf.json
git grep -n -I -E '(from|import) (fridays|agents\.seven|core\.seven_llm|core\.seven_runtime)' -- core frontend agents fridays utils tests
git ls-files -z -- core frontend fridays agents utils lib ops deploy scripts windows desktop android ios ':!*.lock' | xargs -0 -r rg -n --no-heading -e '\b(?:SWARM|SEVEN|FRIDAYS?)_[A-Z0-9_]+\b' -e '(?i)(?:friday_session|seven[-_:]|fridays[-_:]|swarm[-_:]|com\.swarm)'
```

Do not publish environment values, cookies, database rows or tokens with matches.
Use metadata-only fields and bounded redacted outputs in the approved runner.

### C04: hardware/runtime discovery (read-only; no inference)

```bash
grep -H . /sys/class/drm/card*/device/vendor /sys/class/drm/card*/device/device /sys/class/drm/card*/device/mem_info_vram_total /sys/class/drm/card*/device/mem_info_vram_used
grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
ps -C llama-server -o pid,args
curl --max-time 5 --fail-with-body --silent --show-error http://127.0.0.1:8080/health
curl --max-time 5 --fail-with-body --silent --show-error http://127.0.0.1:8080/v1/models
curl --max-time 5 --fail-with-body --silent --show-error http://127.0.0.1:11434/api/ps
curl --max-time 5 --fail-with-body --silent --show-error http://127.0.0.1:11434/api/tags
/home/jd/llama.cpp/build-vulkan/bin/llama-server --version
/home/jd/llama.cpp/build-vulkan/bin/llama-server --help
ollama --version
```

The binary path and endpoints above were observed locally. Reconfirm after
cutover; no `ollama run`, model pull, generation request or server start is
part of C04. Do not print process arguments if a future launcher embeds secrets.

### C05-C09: focused existing tests (isolated test runner only)

Inspect test fixtures for external service/database side effects before running.
Do not point tests at production storage. The new tests required in each task
are proposals until APEX implements them; do not pretend they already exist.

```bash
cd /mnt/archive/projects/swarm
# C05: Studio/teacher baseline
.venv/bin/python -m pytest -q tests/test_deos_teacher.py tests/test_apex_studio.py tests/test_studio_local_teaching.py tests/test_studio_intake.py
# C06: routing and external-service ownership baseline
.venv/bin/python -m pytest -q tests/test_apex_external_server.py tests/test_chat_continuity.py tests/test_model_runtime_gateway.py tests/test_ollama_model_guard.py tests/test_seven_direct_runtime.py
# C07: owner/approval/tool boundary baseline
.venv/bin/python -m pytest -q tests/test_tool_approval.py tests/test_apex_read_tools.py tests/test_local_runtime_policy.py
# C08: frontend and packaging-adjacent baseline
.venv/bin/python -m pytest -q tests/test_frontend_smokes_and_routes.py tests/test_home_chat_continuity.py tests/test_terminal_runtime_contract.py tests/test_windows_launcher_runtime_guard.py
# C09: Studio workflow baseline
.venv/bin/python -m pytest -q tests/test_studio_defaults.py tests/test_studio_projects_git_branch.py tests/test_gemma_studio_watcher.py
```

These are covering baselines, not substitutes for new alias, cookie, scheduling,
model-admission or platform-upgrade tests. Run only the group covering the
current slice; compare pre-existing failures without claiming a passing baseline.

### C10: existing schema inspection (read-only)

```bash
cd /mnt/archive/projects/swarm
sqlite3 -readonly swarm_memory.db '.schema projects'
sqlite3 -readonly swarm_memory.db '.schema project_steps'
sqlite3 -readonly swarm_memory.db '.schema project_step_deps'
sqlite3 -readonly swarm_memory.db '.schema project_docs'
sqlite3 -readonly runtime/studio-evidence.sqlite '.schema studio_evidence'
```

Paths are observed defaults, not authority to bypass the configured connection.
Confirm the live service's selected paths first. This prints schemas, not data;
the APEX wrapper does not currently grant database-shell access.

### C11: review a changed slice (read-only)

```bash
cd /mnt/archive/projects/swarm
git --no-pager diff --check
git --no-pager diff --stat
git --no-pager status --short
```

For exact diff inspection use the attached bounded `get_diff` per approved file,
including untracked source. Stage or commit only after a separate approval.

### C12: conservative UI brand scan (read-only)

```bash
cd /mnt/archive/projects/swarm
git grep -n -I -i -E 'fridays?|seven.s swarm|seven|swarm' -- frontend/templates frontend/static android/seven-app/app/src/main/res/values desktop windows
```

All hits must be classified; no claim that every hit is a rendered string.
Historical quotations, aliases, dependency names and new migration documents
will intentionally keep legacy words. Final acceptance uses the approved
classification ledger, not zero repository-wide grep hits.

## 5. Sequential project tasks

All tasks initially `blocked`, owner `apex`. HB-01 has no task prerequisite;
each later task depends on its predecessor as an operator-approved release
barrier. This deliberate sequence avoids simultaneous namespace and routing
cutovers. Task release does not confer shell, source-write or service authority.

| Task | Exact instruction for APEX | Proof required before completion |
|---|---|---|
| HB-01 | Verify Studio evidence 95 and project `P-26C093E7E6` through actual tools; finish the bounded evidence lookup capability under separate approval if still absent. Use the existing Studio-first curriculum, not another transcript-paging loop. | Exact source receipt IDs, wrong-scope/denied/absent/corrupt tests, bounded long-context response, fresh-turn readback and unseen negative-case pass. |
| HB-02 | Run C01-C03; produce a path/line/class/target/consumer/compatibility/owner/test ledger. Classify brand copy, agent identity, framework module, setting, cookie/token, persistence, service, package identity, history and third-party text. Inspect ignored/untracked source only when authorised. | Stable inventory plus explicit exclusions; all matches in changed scopes accounted for. Never edit from raw counts. |
| HB-03 | Preserve the dirty baseline and define backups/restoration before mutations. Propose SQLite online backups under existing storage policy, including evidence DB; never copy live DB/WAL files as a consistency guarantee. Test restore on disposable storage. Define rollout flag and per-slice rollback. | Operator-approved backup location/retention, restore-test receipt, no production history/session changes, existing edits preserved. |
| HB-04 | Specify canonical map and conflict rules: `seven` agent ID -> `apex`; framework `fridays`/`swarm` -> `hummingbird`; new `HUMMINGBIRD_*` settings; new cookie `hummingbird_session`; old imports/URLs/services readable as aliases. Discover all consumers before deciding each exact mapping. | Reviewed ledger; no `seven` role inheritance, privilege escalation or rewriting immutable authors; simultaneous old/new config conflict fails explicitly unless values are equal. |
| HB-05 | Run C04, inspect registry and actual model artifacts; benchmark approved local orchestrator/coder candidates on held-out tasks. Start with existing small generalists and Qwen2.5-Coder 7B rather than downloading a guessed 24B model. Record licenses/hash/quant/template/schema capability. | Exact candidates, measured accuracy/tool JSON reliability, first-token/total latency, RAM/VRAM peaks at context/concurrency budget, operator model selection. |
| HB-06 | Propose and implement, only after approval, a single host resource-admission owner across llama-server and Ollama. Support GPU lease, bounded CPU/offload policy, draining and external-service ownership handoff. | Tests for unknown telemetry, competing requests/processes, reserve breach, no-swap RAM pressure, cancellation, crash recovery and no killing foreign servers. Operator approves benchmarked thresholds. |
| HB-07 | Make routing feature-flagged and additive. Keep identity `apex`; use task class and an approved model registry to choose orchestrator/coder/backend. Implement handoff/result contracts, bounded fallback and Studio receipt provenance without changing tool authorisation. | Mocked contract tests for roles/schema/denials, task handoff/resume, failover provenance, failed tests never success, same approval at both backends; old route still works with flag off. |
| HB-08 | Canary coding delegation through primary llama-server; exercise eligible CPU/offloaded Ollama fallback and drain/unload/reload with approved server ownership. Preserve source evidence and operator approvals across transitions. | Fresh-turn project continuity, specialist-generated small patch proposal with no unauthorised apply, exact model/backend labels, no duplicate heavy model residency or OOM, measured latency/resource acceptance. |
| HB-09 | Add canonical identity/config readers before changing writers. Normalize only known legacy IDs at API/routing/ACL boundaries. Centralize tested environment-key precedence and read-side historical mapping. | C06/C07 plus new tests: old Seven request resolves APEX with same permissions, spoofed/unknown identity denied, new key wins only by explicit conflict policy, no historical row edits. |
| HB-10 | Migrate both authentication mechanisms and every consumer together. New owner logins emit `hummingbird_session`; legacy `friday_session` remains validated until its existing expiry. Share validated-token selection with chat approval and SSE. Keep opaque random tokens; do not brand or weaken token bytes. | Old/new/expired/revoked/collision tests, unchanged signing keys/TTL/role checks, consistent owner identity and approval hash, logout cannot resurrect a legacy cookie, existing sessions remain untouched. |
| HB-11 | Make future primary-agent writes canonical `apex` and new wrapper metadata `hummingbird`. Update defaults/registry/authorisation accordingly. Keep historical joins and permission checks aware of aliases without rewriting historical authors or active thread state. | New task/message/receipt/ACL fixtures canonical; old rows still queryable and correctly scoped; active project ID/snapshot/approval association stable; no duplicate agent profile with divergent rights. |
| HB-12 | Rename rendered web/mobile/desktop product copy to Hummingbird and primary-agent labels to APEX. Use C12 to inspect exact strings, localisation, accessibility labels, headings, notifications, page titles and login/help screens. | C08 plus UI canary screenshots/accessibility checks; old historical messages unchanged, no dead links; no brand replacement inside third-party assets. |
| HB-13 | Move Python first-party framework namespaces to `hummingbird` and agent-specific implementation to `agents.apex` in one reviewed module slice at a time. Temporary old modules re-export canonical implementations without duplicate singleton/registry state. Preserve external import compatibility. | Import/dependency tests in both names, one implementation/dispatcher/lock registry, no circular imports, C05-C07 covering changed slices; exact path ledger and reviewed patch receipts. |
| HB-14 | Stage service/CLI/path/settings cutover: Hummingbird commands and units, canonical logging/lock names, updated launchers/config/docs. Same live DB and state remain selected; no new empty store. Use shared lock identity during mixed-version operation and only one live service per endpoint. | Dry-run deploy/config tests, no secret logging, old entrypoint alias works, state-path compatibility and duplicate-service prevention, operator-approved restart/canary and rollback receipt. |
| HB-15 | Plan first-party Python distribution, Android namespace/application ID, desktop bundle ID, iOS/Windows package names separately from branding. Decide exact reverse-domain owner and signed-upgrade strategy with operator; keep old installed IDs as compatibility contracts until migration is validated. | Explicit package-ID/signing/data-migration approvals; isolated platform builds and old-install upgrade/data test. Unsupported platform or unavailable signing blocks this task, never silently skips it. |
| HB-16 | Sweep active docs/examples/CI/first-party skills for canonical paths and product language; update discoverability links and build artifacts. Preserve factual history, Git history, published old URLs, third-party packages, model IDs and necessary alias references. | Link/import/build checks, classified remaining-hit ledger and C11; downloads/generated caches excluded, no unrelated dependency updates. |
| HB-17 | Execute the complete migration matrix in isolated fixtures, then approved UI canary. Cover both config namespaces, both cookies, aliases, immutable history, new writes, current/old imports, primary/fallback routing, memory admission and installed-client contracts. | Measurable matrix with exact commands/output/exit/model/receipts; first failed required assertion blocks closeout. No full-suite claim from selected tests. |
| HB-18 | Cut over under operator control: activate canonical writers/routes/service entrypoints in the reviewed order; monitor admission, permissions, sessions, index/task continuity and UI. Roll back the approved slice on a failed invariant. | Operator release and deployment receipts; observed old-session access/new Hummingbird cookie; APEX canonical writes; coder routing/provenance; no record/token rewriting or autonomous restart. |
| HB-19 | Observe legacy alias usage for a full configured compatibility window. Remove only first-party aliases whose consumers and old-version readers are proven retired, with explicit operator approval. Legacy sessions remain accepted until natural expiry; indefinite external consumers mean retained aliases. | Alias-call counters without secrets, evidence of old token expiry and client upgrade, compatibility retirement decision per key/path/endpoint. Never remove by calendar guess. |
| HB-20 | Re-run scoped inventory; close only when every remaining legacy hit is intentional history, third-party text, tested compatibility or an explicitly approved unresolved contract. Attach final readback evidence, rollback references and residual risks in Studio. | No unclassified active first-party namespace; fresh-turn APEX retrieves final evidence; operator signs off. Deferred contract migration means project partial/blocked, not completed. |

## 6. Dynamic model routing and 16 GB admission design

### Identity is not the weights

APEX remains the canonical orchestrator identity even when its serving model
changes. A small generalist is a **candidate**, not an automatic downgrade.
Evaluate 3B-8B models for classification, strict tool envelopes and evidence
handling; current gpt-oss behaviour is the baseline. Normal chat/orchestration
does not author migration patches. A specialised coder receives bounded
assignments; it does not gain a separate mutable Studio identity or ACL.

Start coder evaluation with the already available `qwen2.5-coder:7b` and the
registered `apex-direct:7b` artifact after confirming they really match. Consider
other Qwen/Mistral/DeepSeek models only with exact artifact, license, supported
template and measured task results. Neither “specialists always outperform”
nor “quantisation necessarily destroys logic” is established by this audit.
The quoted Devstral model/version/size and claim about VS Code internals are
not verified facts and are not deployment instructions.

### Handoff contract APEX must propose, test and implement

Required request fields: request/task/project/conversation IDs, canonical owner,
role `coder`, bounded task specification, approved path list, baseline revision
and dirty-file fingerprints, source receipt handles, approved model/profile,
token/context/time/output budgets, and required acceptance tests.

Required response fields: same task/request identity, exact model artifact,
backend and quantisation, status, proposed patch reference/hash, read/test
receipts, resource peaks, verified outcomes, uncertainties and blockers.

Do not send full historical transcripts, credentials or arbitrary filesystem
contents. Reject stale baselines, mismatched identities and unknown fields.
Store the handoff before inference. Specialist output is untrusted proposed
code; never execute returned shell text. Preserve existing approval transaction
binding and source fingerprints. APEX reports test failure; it cannot change
the acceptance criterion to make the answer pass.

### Resource invariant (all values measured on the selected GPU)

Admission requires BOTH:

1. `current_device_used + incremental_job_peak + gpu_reserve <= device_total`
2. `incremental_host_peak + host_reserve <= MemAvailable`

Incremental peaks include weights not already resident, KV cache at the actual
context and slot count, scratch/compute buffers and concurrency overhead.
Do not double-count the measured desktop in both current usage and a model
estimate, or omit it. Do not sum unrelated GPUs to satisfy one model's budget.

Initial **proposed** floors for benchmarking: 2 GiB spare VRAM and 8 GiB
MemAvailable after admission; one coding slot; orchestrator context 4,096,
coder initial context 4,096, promote to 8,192 only after measured acceptance.
The 16 GB label is not an allocation allowance. Tighten floors after measuring
desktop peaks; operator approval is needed before changing them. Unknown/stale
telemetry blocks GPU admission. Model file size is not runtime memory.

System RAM is not GPU VRAM. Prefer intentional CPU layers/offloaded KV over
accidental GTT/driver spill. The observed machine has no swap: reserve RAM
for OS/UI/SQLite and decline work instead of relying on swap or kernel OOM.
Reduce batch/context or queue work before expanding budgets. Do not truncate
the current request, required schema or source evidence to fit a specialist.

### Scheduling state machine (host-enforced)

`classify -> validate contract -> checkpoint Studio -> acquire resource lease
-> drain owned GPU workload -> verify release -> admit coder -> infer proposal
-> verify/test through approved tools -> persist receipt -> release lease
-> restore orchestrator serving route -> resume`

- Keep the lightweight orchestrator CPU-resident only if its latency/RAM
  benchmark passes, or checkpoint and unload it during GPU coder use. A tiny
  GPU-resident orchestrator plus coder is allowed only after joint measurement.
  No assumption that both fit; “APEX stays resident” does not mean GPU-resident.
- In the current fixed-model external service, changing models requires an
  approved drain/restart or a newly approved serving configuration. The current
  APEX backend is external to the Python pool: never kill it as a foreign server,
  repurpose its port or spawn a second copy automatically.
- Fallback eligibility: transport/startup failure or measured resource
  infeasibility after bounded primary attempt, not permission denial, malformed
  tools, failed tests or unsafe output. One eligible fallback per request;
  open a circuit after failure and stop rather than alternate daemons forever.
- Ollama may use the same GPU. Admit it under the same lease and measured
  budget; prefer an explicitly tested CPU-only profile when primary GPU is
  occupied. If the task cannot meet RAM/latency/context budget, queue or block.
- Never silently replace one model with another: show original model, selected
  fallback, backend and cause in Studio/UI. Preserve APEX identity and original
  tool permissions regardless of model/provider.
- Cancellation, timeout and daemon crash release only supervisor-owned
  resources after verification. Persist state before model unload; response
  schema failure or a missing patch/test receipt is not a completed task.

### Offload parameters confirmed in this installed binary

APEX must propose reviewed profiles using these observed flags, not guess an
executable launch command:

| Setting | Intended use and required evidence |
|---|---|
| `--n-gpu-layers 0` | CPU weights baseline; pair with `--no-kv-offload` if a no-GPU KV profile is required. Verify actual allocation. |
| `--n-gpu-layers N` | Partially offload measured layers; choose N from model-specific trials, never derive N from parameter count alone. |
| `--ctx-size 4096` / `8192` | Start bounded; measure KV/scratch peaks at the real maximum prompt, not idle health. |
| `--parallel 1` | One coding slot initially; test concurrent request rejection/queuing. |
| `--threads N` | Pick from measured CPU topology/latency and UI contention; no universal thread count. |
| `--cache-type-k` / `--cache-type-v` | Candidate KV compression only after backend support and quality validation; not a free precision change. |
| `--fit on`, `--fit-target` | Installed auto-fit support; inspect actual chosen settings. It is not a replacement for host admission or an approval to shrink required context silently. |

Ollama candidate requests may specify `options.num_gpu = 0`, `num_ctx` and
bounded output/keep-alive under the approved adapter. Confirm those fields are
effective for the exact version/model via `/api/ps`, `ollama ps` and live memory;
labels such as `fred-cpu` are not proof. No fallback daemon changes in this plan.

Primary references: [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)
and [Ollama FAQ](https://docs.ollama.com/faq). Installed `--help` and measured
behaviour take precedence over assumptions based on newer upstream examples.

## 7. Compatibility policies APEX must implement after approval

Proposed canonical path map for HB-04 review (not permission to move files):

| Existing first-party path/contract | Proposed canonical target | Required compatibility |
|---|---|---|
| `fridays.*` framework modules | `hummingbird.orchestration.*` | Old import shims delegate to the same module state. |
| `core.seven_llm.*` | `hummingbird.llm.*` | Preserve gateway/registry signatures and external model aliases until tested. |
| `core.seven_runtime.*` | `hummingbird.runtime.*` | Preserve old HTTP/launcher contracts while canonical clients migrate. |
| `agents.seven.*` active primary-agent implementation | `agents.apex.*` | Reconcile the already-existing `agents/apex` implementation; never overwrite it with a directory rename. Historical Seven diaries/records remain history. |
| `swarm-terminal.service`, `swarm-fridays.service` | `hummingbird-terminal.service`, `hummingbird-orchestrator.service` | Reviewed unit aliases and one process per endpoint; installed ownership discovered before cutover. |
| `SWARM_DB_PATH` | `HUMMINGBIRD_DB_PATH` | New configuration may still select the same existing `swarm_memory.db`. |
| `SEVEN_LLAMA_SERVER_HOST` | `HUMMINGBIRD_LLAMA_SERVER_HOST` | Exact typed resolver; classify every other key rather than blindly rewriting prefixes. |
| `friday_session` | `hummingbird_session` | New issuance, dual validation, unchanged active token records and expiry. |

These are source/entrypoint targets, not claims that new modules or units exist.
HB-02 must enumerate every descendant and consumer, and HB-04 approves the
complete map before any slice moves. Installed package IDs and distribution
names remain HB-15 decisions, not guessed reverse-domain targets.

- **Agent identity:** canonicalise known aliases before lookup/ACL evaluation,
  but authenticate the caller first. An alias cannot turn an agent or anonymous
  request into an owner. New authorisations explicitly target `apex`; old grants
  resolve to the same effective principal without duplicating privilege records.
- **Config:** new `HUMMINGBIRD_*` key plus exact legacy alias, one resolver and
  shared validation. If both differ, fail with redacted conflict; if equal,
  accept and emit a bounded deprecation receipt. Retain external `OLLAMA_*`,
  `LLAMA_ARG_*` and third-party environment names unchanged.
- **Cookies:** the name becomes `hummingbird_session` for new issuance, not a
  readable brand prefix in the random token. Dual-read old/new cookies, preserve
  original TTL/security attributes, validate each server-side, explicitly reject
  conflicting principals, and use the same chosen validated token for owner,
  SSE and approval binding. Do not silently downgrade an invalid new cookie.
  Logout revokes all valid presented credentials and clears both cookie names.
- **Storage:** historical physical files/tables/keys are compatibility storage,
  not branding. New canonical config may point to the existing old-named file;
  do not rename a live WAL database. New installations can select canonical
  filenames after a separately tested path-resolution change. New rows use
  canonical IDs; existing snapshot digests/project IDs/session records remain
  intact. An alias-read must preserve owner/conversation isolation.
- **Imports/services:** canonical modules own state; old shims delegate rather
  than copy registries. Mixed-version processes must share the same lock while
  draining; no separate old/new locks permitting double loads. One bound service
  per port; unit aliases cannot launch duplicate daemons.
- **Packages:** changing Android applicationId or desktop/iOS bundle ID often
  creates a new application rather than an in-place update. Require exact
  publisher namespace, signing continuity, export/import and update strategy.
  Historical installed IDs may remain compatibility exceptions; no silent data
  loss and no claim that changing a manifest string migrates installations.
- **History/third parties:** retain immutable sources and quotations. Published
  GitHub remote ownership and third-party model/package names are not renamed.
  Do not remove words like “seven” from ordinary prose/numeric fixtures.

## 8. Studio ingestion and review gate

Existing mapping:

| Manifest field | Existing Studio target |
|---|---|
| `project.name`, `description`, `methodology`, `owner`, `status`, `tags` | `projects` row, owner explicitly `apex`, status `on_hold` |
| `steps[].key/title/description/owner/order_idx/status` | `project_steps`; key retained in title/description, status `blocked` |
| `steps[].depends_on` | `project_step_deps` using registered step IDs |
| `document` and manifest contents | New `project_docs` rows, associated by `project:<id>` tags |
| registration/verifications | `project_blackboard_notes` and Studio evidence ledger |

Use an atomic registration against the verified configured Studio database:
insert the project directly as on hold and tasks directly as blocked, register
all dependencies and documents, commit, then independently read them back.
The current convenience `create_project` helper initially creates an active
project; do not create an avoidable active interval. No schema changes and no
edits to existing historical projects/sessions are needed for this registration.
Use a stable manifest key and exact content comparison for retry safety.

Studio project hold is **not** a substitute for tool approvals. No background
worker is enqueued. The current open-task selector omits project status, so do
not release a task to `todo` until the operator explicitly releases both the
project and that task and the effective executor gate has been verified.
Fix scheduler hold enforcement as part of the Phase 1 gate before automatic
pickup is ever enabled. Do not assume dependency rows alone enforce scheduling.

Registration acceptance: project on hold; exactly 20 manifest task rows blocked
and owned by apex; 19 predecessor edges; Markdown and JSON doc readback hashes
match disk; no inference/model/source/service action started by registration;
project visible via the existing Studio project API/UI.

## 9. Strict stop conditions

Missing permission/tool/model provenance; conflicting worktree edits; missing
or corrupt evidence; incomplete backup/restore; cross-owner reads; unexplained
alias conflict; old session invalidated; unverified model unload; unknown/stale
memory; reserve breach; wrong primary/fallback provenance; absent platform test;
or a required failed assertion stops the affected task. Record exact receipts.

Do not claim completed migration while a first-party external contract remains
unresolved. Necessary aliases/history/third-party names are intentional,
classified exceptions, not permission for new legacy writers.

DEOS contract: `legacy_eagerness_check = true`; technical constraints and
authorised procedures are above; `prohibited_execution_code = null`. Bash
blocks are bounded diagnostics/test instructions, not a rename implementation.
