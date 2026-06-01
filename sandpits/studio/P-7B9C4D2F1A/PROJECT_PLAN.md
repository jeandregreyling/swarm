# Browser-First Runtime Stabilization — Dell + Samsung (P-7B9C4D2F1A)

**Status:** active  
**Owner:** Seven  
**Created:** 2026-05-28  
**Methodology:** Browser-first stabilization, wrapper-second

---

## Overview

Stabilize Fridays and adjacent SWARM surfaces in browser mode on Windows Dell
and Samsung/Potato targets before spending more time on desktop/app wrappers.
The immediate rule is simple: if the browser path is broken, the app wrapper is
noise. Fix runtime, routing, startup, storage, and UI regressions first. Revisit
packaging only after browser parity is acceptable.

This project owns:
- Dell Windows browser-first Fridays runtime
- Samsung/Potato browser-first access path
- cross-platform startup defects exposed by browser use
- Studio-visible bug tracking for runtime/UI regressions

This project does not yet own:
- final desktop packaging polish
- Tauri/PyInstaller hardening beyond what is required to keep browser fallback alive
- unrelated feature work outside runtime stabilization

This project now also owns:
- the documented transition plan from WSL-tunnel execution to native
  Windows-native + Linux-native repo copies on the same physical potato
- the explicit responsibility split between Studio, Git, and Vortex for
  cross-node operation
- the sequencing rule that Windows/browser stabilization finishes before the
  repo-topology split is implemented

---

## Change Log (Plain English - What, When, Why)

**May 28, 2026 - Project opened**
- Created a dedicated Studio project for browser-first stabilization after the
  Dell Windows path proved reachable through browser runtime but not clean as a
  desktop app.
- Scope includes Dell now and Samsung/Potato next, using the browser as the
  stable execution surface while app wrappers are repaired in parallel later.
- **Why:** runtime bugs are easier to isolate in browser mode; app shell failures
  were hiding actual backend/startup defects and wasting time.

**May 28, 2026 - Dell Windows launch path unblocked**
- Added a WSL-safe Windows launcher path via `windows/run-fridays-from-wsl.sh`.
- Updated `windows/start-fridays.bat` to auto-run first-time install instead of
  failing on missing `.venv-win`.
- Updated `windows/install-fridays.bat` to support non-interactive runs and
  optional Ollama pull skipping.
- Moved Windows runtime DB usage onto `%LOCALAPPDATA%\Fridays\swarm_memory.db`
  for launcher/runtime consumers that respect `SWARM_DB_PATH`.
- Hardened `windows/launcher.py` so browser fallback survives `pywebview` path failures.
- **Why:** the old path assumed a clean Windows local repo layout and a working
  webview shell. That assumption was false on this Dell setup.

**May 28, 2026 - Dell browser smoke audit (Packet 1, partial)**
- Verified Windows-side success for:
  - `/ui`
  - `/studio`
  - `/library`
  - `/chat`
  - `/monitor`
  - `/api/tasker/tasks`
  - `/api/auth/me`
  - `/api/auth/setup-status`
  - `/api/swarm/status`
  - `/_health`
- Verified the main shell still references the expected browser assets for
  projects, chat, library, tasker, Windows CSS, and auth bootstrap.
- Confirmed some initial 404 probes were false alarms caused by probing the
  wrong endpoints rather than actual frontend contract failures.
- Identified one live browser blocker still failing on Dell Windows:
  - `/api/hive/nodes` times out consistently even after moving Hive storage to
    `%LOCALAPPDATA%\\Fridays\\swarm_hive.db`

**June 1, 2026 - Agent availability clarity pass**
- Surfaced explicit agent availability reasons through `/api/agents/config`
  so Chat and Agents can distinguish ready agents from disabled/offline ones.
- Chat agent tiles now show availability text instead of flattening everything
  into a vague unavailable state.
- Remaining blocker is still real runtime reachability: local models and paid
  keys must actually be present for some agents to answer.
- Added defensive runtime changes:
  - Windows launcher now exports `SWARM_MEMORY_DB`
  - Windows launcher now exports `SWARM_HIVE_DB`
  - Hive nodes route now contains bounded/fallback logic, though the Windows
    timeout path still required a deeper fix at the time of this checkpoint
- **Why:** establish which browser surfaces are actually broken before touching
  Samsung/Potato or spending more effort on wrapper packaging.

**May 28, 2026 - Dell Windows listener hygiene fix**
- Root cause for the unstable Hive route was not a permanently broken endpoint;
  it was repeated Windows starts spawning duplicate Python listeners on port
  `5050`, creating non-deterministic behavior depending on which process
  answered a request.
- Fixed `windows/start-fridays.bat` to reuse an existing healthy runtime:
  - probe `/_health`
  - if healthy, open `/ui` and exit cleanly
  - do not spawn another launcher process
- Verified after fix:
  - only one listener remains on `127.0.0.1:5050`
  - repeated `start` calls do not create duplicates
  - `/api/hive/nodes` returns `200` quickly from the clean runtime
- **Why:** Windows browser stabilization is impossible if every start command can
  silently fork another server on the same port.

**May 28, 2026 - Dell Windows broad tile sweep**
- Added a browser sweep runner at `windows/ui_tile_sweep.py` to open every
  visible home tile on the Windows browser runtime, click obvious tab strips,
  and record bad responses / console failures into
  `windows/artifacts/tile-sweep-report.json`.
- Sweep outcome on the clean Windows runtime:
  - clean on first-pass open: Chat, Terminal, Knowledge, Trace, Vortex shell,
    Access shell, Potato Farm, Feeds, Money Hub
  - still broken or noisy:
    - auth overlay still blocks browser interaction when no active session
    - Media Center bottom tabs are not clickable because other panes intercept
      pointer events
    - contextual Seven reasoning calls can hang/fail from some tiles under
      Windows load
    - Monitor/diamond runtime still logs Windows `psutil` temperature errors
- Used the sweep to isolate and fix two adjacent Windows issues:
  - non-prod Git panels now degrade as `available=false` instead of hard `500`
  - App Center project listing now uses `SWARM_DB_PATH` with SQLite WAL /
    busy-timeout handling
- **Why:** this moved the stabilization stream from anecdotal breakage reports
  to a repeatable browser-surface audit with an explicit defect list.

**May 28, 2026 - Regression fence started for cross-platform runtime hardening**
- Added focused regression coverage for the hardened browser/runtime changes so
  the Windows fixes do not quietly break Linux:
  - `tests/test_git_branch_mirror.py` now pins handled `available=false`
    responses when non-prod Git worktrees are missing or unavailable on the
    current runtime.
  - `tests/test_hive_blueprint.py` now pins the Windows-only Hive node
    DB-fallback path and `source='db-fallback-windows'`.
- Re-ran the focused slice in the repo `.venv`:
  - `tests/test_git_branch_mirror.py`
  - `tests/test_studio_projects_git_branch.py`
  - `tests/test_hive_blueprint.py`
  - `tests/test_hive_install_routes.py`
  - `tests/test_hive_installer_core.py`
- Confirmed the current implementation remains Linux-safe by design:
  - `frontend/blueprints/hive.py` only forces direct DB reads when
    `SWARM_PLATFORM=windows`; Linux still uses the registry path first.
  - `frontend/blueprints/git.py` keeps `prod` bound to the live repo root and
    only downgrades missing `dev`/`uat` worktrees into handled availability
    responses.
  - env-driven DB paths remain defaults, not Windows-only rewrites.
- Operational rule updated for this project: every material step must be logged
  back into Studio immediately, not treated as optional.
- **Why:** browser-first stabilization needs a regression fence and a durable
  Studio trail, otherwise the Windows fixes drift and the Linux contract gets
  broken by accident.

**May 28, 2026 - Browser click sweep expanded on live Linux runtime**
- Brought up a clean local Fridays runtime on `:5050` and ran two browser
  automation passes against the real UI:
  - `windows/ui_tasker_smoke.py`
  - `windows/ui_surface_exhaustive.py`
- Added `windows/ui_surface_exhaustive.py` as a broader non-destructive tile
  click harness. It opens every visible home tile and walks safe visible
  controls with a per-tile time budget.
- To get Playwright running inside this WSL environment without root package
  installs, staged local browser host libs under `.cache/local-libs/` and ran
  the sweeps with `LD_LIBRARY_PATH` pointed at the extracted Debian libs.
- Tasker smoke result:
  - the UI flow itself passed end-to-end
  - create, search, filter, edit, toggle, run, evidence refresh, and delete all
    worked at the browser level
  - backend still emitted `500`s during the run:
    - `/api/ollama/models`
    - `/api/tasker/tasks/20/run`
- Exhaustive tile sweep result:
  - all visible home tiles opened
  - the harness still needs selector hygiene because generic control capture is
    hitting window chrome/shared controls before tile-specific buttons on some
    surfaces
  - despite that, the run still exposed real backend/runtime failures:
    - `/api/ollama/models` returns `500` when Ollama is not reachable
    - `/api/git/status?check_remote=1` can block/fail from browser surfaces
    - the server stdout shows interactive SSH host authenticity prompts being
      triggered by remote Git checks, which is unacceptable in a web request
- Linux compatibility check remains intact:
  - these findings are cross-platform runtime problems, not Windows-only hacks
  - the browser sweeps were run against the Linux-hosted local runtime, so the
    current failures are reproducible outside the Dell Windows shell path too
- **Why:** the project needed a real “click through everything” pass on a live
  runtime, not just route probes and tile-open smoke.

**May 29, 2026 - Architecture split agreed and logged before implementation**
- Confirmed the ownership model:
  - Git is the repo owner and canonical code history
  - Vortex is the local time-machine / operational state ledger
  - Studio is the operator control surface over both
- Confirmed the near-term topology target:
  - `potato-1-linux` and `potato-1-win` will be separate registered farm nodes
    even when they share the same physical machine
  - Windows must stop depending on the Linux repo through WSL filesystem
    tunnelling
  - Windows will get its own native local clone
  - Linux will keep its own native local clone
  - for now both will sync against GitHub as the upstream transport
- Confirmed the future transport target:
  - GitHub remains the active sync transport now
  - local-first transport between potatoes is a later phase
  - Vortex should track drift, sync state, deployed SHA, and node-local changes
    but should NOT become a second canonical code store
- Confirmed runtime/model assumption:
  - Ollama model assets currently live on the shared NTFS drive visible to both
    Linux and Windows
  - Windows agent/runtime validation against that shared model path is still a
    deferred verification item because Windows Fridays is still in stabilization
    mode
- Sequencing rule locked:
  - first fix the Windows/browser/runtime defects
  - then implement the Windows-native repo split and transport cleanup
  - then add broader architecture changes for local-first cross-potato sync
- Documentation rule reinforced:
  - if it is not written in Studio, it does not exist for this project
- **Why:** the runtime is still too unstable for topology surgery; logging the
  architecture now prevents improvised changes later.

**May 29, 2026 - Browser poison routes cleaned up and Tasker smoke turned green**
- Fixed the two backend contracts that were poisoning multiple browser surfaces:
  - `frontend/blueprints/git.py`
    - remote fetches used by browser status checks are now non-interactive
    - `check_remote=1` degrades into `remote_check.ok=false` instead of hanging
      or throwing a hard `500`
    - fetches now run with terminal prompting disabled and a bounded SSH
      connect timeout
  - `frontend/blueprints/ollama.py`
    - `/api/ollama/models` now degrades as a `200` payload with
      `ok=false,running=false,models=[]` when Ollama is offline, instead of a
      hard `500`
- Added regression coverage:
  - `tests/test_git_branch_mirror.py` now pins fail-soft remote status
  - `tests/test_ollama_models_contract.py` now pins the degraded Ollama models
    contract
- Revalidated on the live runtime:
  - `/api/git/status?check_remote=1` now returns `200`
  - `/api/ollama/models` now returns `200` with degraded payload
- Fixed browser harness issues:
  - `windows/ui_tasker_smoke.py` now uses an OS-appropriate shell command
    instead of forcing a Windows `cmd /c` payload against a Linux-hosted run
  - `windows/ui_surface_exhaustive.py` now scopes selectors to the current tile
    correctly and skips shared window chrome before attempting tile-local
    controls
- Rerun outcome:
  - `windows/ui_tasker_smoke.py` is now fully green end-to-end on the live
    runtime
  - `windows/ui_surface_exhaustive.py` no longer reports backend Git/Ollama
    failures; remaining failures are mostly tile-local click/intercept behavior
    and content/state issues
- **Why:** backend route poison had to be removed first, otherwise every tile
  sweep kept reporting the same non-UI failures and the evidence was garbage.

---


**June 1, 2026 - Windows launcher runtime reuse guard**
- Added `_is_healthy()` and `_open_browser()` to `windows/launcher.py` so a healthy runtime is reused instead of spawning duplicate listeners.
- Added `tests/test_windows_launcher_runtime_guard.py` to pin the guard before splash/server startup.
- Validation: `python -m pytest -q tests/test_windows_launcher_runtime_guard.py` passed; `python -m py_compile windows/launcher.py tests/test_windows_launcher_runtime_guard.py` passed after fixing the CURRENT_FOCUS seed string.
- Broad UI sweep ran against the live runtime; remaining issues are mostly tile-local pointer interception and overlay noise in Chat/Knowledge, not backend startup failures. Report: `windows/artifacts/ui-surface-exhaustive-report.json`.

**June 1, 2026 - Windows packaged app drift + empty venv failure chain**
- Live operator symptom after "restart":
  - Chrome and the Windows app showed Agents/Services/VPN/Vortex failures at
    the same time
  - roster appeared truncated/missing (`duck`, `qwen`, paid/API agents)
  - Services panel had nothing actionable to restart
- Root cause was not missing source routes.
  - Fresh backend probe from the repo runtime returned `200` for:
    - `/api/agents/config`
    - `/api/agents/ops-summary`
    - `/api/services`
    - `/api/vpn/status`
    - `/api/time/timeline`
  - Source contract confirms Vortex uses `/api/time/...`, not `/api/vortex/...`
- Actual failure chain:
  - the Windows app/runtime was not aligned with the repo runtime
  - the launcher could previously reuse the wrong healthy `:5050` process
  - after the app was closed and restarted from WSL, the Windows-side
    `.venv-win` turned out to be effectively empty (`pip` only, no `flask`)
  - launcher thread then died before binding `5050` with:
    - `ModuleNotFoundError: No module named 'flask'`
- Actions taken:
  - committed runtime-id guard + launcher support files:
    - `a5314f35` `Fix Windows runtime reuse and add launcher support files`
  - committed installer/docs/test follow-up:
    - `03e2d88f` `Document Windows launcher flow and cover runtime guard`
  - brought the repo backend up from WSL/Linux `.venv` and verified the full
    route contract live on `127.0.0.1:5050`
- What still must be fixed for the Windows app path:
  - installer/bootstrap must leave `.venv-win` with the real app dependencies,
    not just `pip`
  - packaged/native app launch must prove it is serving the same frontend and
    backend generation as the repo source
  - Windows launch flow needs a deterministic health check that fails loudly on
    missing Python deps instead of opening a broken shell
- Immediate operator-safe fallback:
  - run the repo runtime from WSL/Linux `.venv` and use Chrome against
    `http://127.0.0.1:5050/ui`
  - treat the packaged Windows app as untrusted until build/install parity is
    revalidated

**June 1, 2026 - UI sweep click fallback improved**
- Updated `windows/ui_surface_exhaustive.py` so each tile is re-focused before the click pass and pointer-intercepted controls retry with `force=True`.
- Rerun result: Chat and Knowledge now click through cleanly; remaining report noise is mostly budget exhaustion and benign text capture in Terminal, not blocked controls.
- Validation: reran `windows/ui_surface_exhaustive.py` against the live runtime after `python -m py_compile windows/ui_surface_exhaustive.py` passed.

**June 1, 2026 - Samsung/Potato route check**
- Verified the live tablet-facing surfaces directly: `/api/hive/install/android` returns `200` with the Seven for Android landing page, and `/api/hive/install/seven-app.apk` plus `/api/hive/install/swarm-hive.apk` both return non-empty APK payloads.
- Added `tests/test_hive_install_routes.py::test_install_android_page_promotes_tablet_apk` to pin the Android landing page content, APK links, and Samsung S9 FE wording.
- Focused tablet-path pytest slice passed for install routes, Termux tarball delivery, expected node roster, and Samsung NPU detection.
## Packets

- [ ] Packet 1 — Dell Windows smoke audit: verify browser-first operation across Studio, Chat, Library, Tasker, Agent status, auth/session, static assets, and route health
- [ ] Packet 1B — Dell Windows broad tile sweep: keep browser-first coverage across all visible home tiles and log obvious regressions before deeper module passes
- [x] Packet 1A — Dell Windows Hive/Monitor fix: restore reliable `/api/hive/nodes` responses so monitor and potato views stop blocking in browser mode
- [ ] Packet 2 — Dell Windows startup debt: reduce or eliminate startup-time database lock warnings, duplicate listeners, and background daemon collisions
- [ ] Packet 3 — Dell Windows storage/path audit: identify remaining code paths that ignore `SWARM_DB_PATH` or assume Linux-native paths during Windows runtime
- [ ] Packet 4 — Samsung/Potato browser path: verify access pattern, route health, device-specific UI issues, and capability/reporting integrity when driven from browser instead of app shell
- [ ] Packet 5 — Cross-platform wrapper backlog: catalogue what still breaks in `pywebview`, packaging, localhost forwarding, and device app wrappers after browser mode is stable
- [~] Packet 6 — Regression fence: add focused tests for Windows/browser launch assumptions and any runtime fixes made during this stabilization stream
- [ ] Packet 6B — Windows packaging parity: prove `.venv-win` bootstrap installs the full app stack and that packaged/native launches expose the same route + asset generation as source
- [ ] Packet 7 — Windows-native repo split plan: define native clone layout, node IDs, sync rules, and GitHub-backed transport without cutting over yet
- [ ] Packet 8 — Vortex/Git role fence: record the Vortex state schema, Git ownership boundary, and Studio views needed for cross-node comparison

---

## Execution Order

| Priority | Packet | Risk if skipped | Notes |
|---|---|---|---|
| 1 | Packet 1 — Dell Windows smoke audit | High | No clear defect list |
| 2 | Packet 2 — Dell Windows startup debt | High | Runtime instability |
| 3 | Packet 3 — Dell Windows storage/path audit | High | Hidden Windows breakage |
| 4 | Packet 4 — Samsung/Potato browser path | Medium | Next platform blocked |
| 5 | Packet 6 — Regression fence | Medium | Fixes drift/regress |
| 6 | Packet 6B — Windows packaging parity | High | Packaged app can lie about runtime health |
| 7 | Packet 5 — Cross-platform wrapper backlog | Low | Wrapper polish can wait |
| 8 | Packet 7 — Windows-native repo split plan | Medium | Architecture drifts if undocumented |
| 9 | Packet 8 — Vortex/Git role fence | Medium | Ownership confusion breeds split-brain |

---

## Architecture Decisions

### Canonical Ownership

- Git owns the code, commit graph, branches, merges, and diff truth.
- Vortex owns time-machine state, node-local event history, deploy/sync state,
  and drift observations.
- Studio owns the operator surface and must expose both Git truth and Vortex
  truth without making them compete.

### Node Identity

- Physical host: `potato-1`
- Runtime nodes:
  - `potato-1-linux`
  - `potato-1-win`

The same physical machine may host multiple farm nodes when the runtime,
filesystem, and dependency surfaces are materially different.

### Near-Term Transport

- Upstream transport: GitHub
- Local native repos:
  - one Windows-native clone
  - one Linux-native clone
- WSL path tunnelling is a bootstrap convenience only, not the target runtime
  architecture

### Future Transport

- GitHub can later be swapped or supplemented by:
  - local bare origin
  - Fridays always-on cloud relay
  - potato-to-potato transport

The Studio mental model should remain stable even if the transport changes.

### Explicit Non-Goals

- Vortex is not a Git replacement
- Fridays is not trying to become a full VS Code clone
- custom code-history storage inside Vortex is out of scope except for evidence,
  patches, snapshots, and operational metadata

---

## Blackboard

- Standard path for Dell from WSL is now `./windows/run-fridays-from-wsl.sh start`
- Browser-first is the temporary production path for this stabilization stream
- Windows localhost serving was confirmed; WSL localhost forwarding is still not
  a trustworthy health probe on this machine
- Known current defect classes:
  - startup-time SQLite lock warnings
  - stale listener/process cleanup after repeated failed launches
  - `pywebview` path/base-uri failure on WSL-backed repo paths
  - mixed DB path assumptions across modules
- Samsung/Potato should be treated the same way: validate browser path first,
  then repair app shell once runtime and UI are clean
- Studio logging is mandatory for this project; local work without project-plan
  writeback is considered incomplete
- Shared Ollama model storage across Windows/Linux is accepted for now, but the
  Windows agent/runtime path still needs explicit validation before it can be
  treated as reliable
- Hooks are allowed as transport/policy glue, but they are not the architecture;
  Git remains the code authority and Vortex remains the operational ledger
- Ghost logging is active again for human chat prompts. Owner-session prompts
  are now attributed to the human alias (`jeandre` via display-name/session
  resolution) instead of being flattened into anonymous `ghost` sludge.
- Windows/agent validation now has live benchmark evidence:
  - local Ollama-backed agents (`qwen`, `llama`) fail fast in ~0.05-0.09s with
    explicit unreachable responses while Ollama is down
  - `nine` currently returns upstream `403 Access denied` in ~1.3s
  - `scholar` is not directly routable from `/api/chat` because service-tier
    agents are intentionally excluded from the user-routable set
- Agent status contracts were hardened so local agents no longer advertise
  idle/online when the local Ollama runtime is offline. `/api/agents/config`
  now reports those local agents as `offline`, and `/api/agents/status` now
  marks enabled-but-unreachable local agents as `down`.
- Browser probe after runtime restart confirmed the Chat home tile opens again
  via normal pointer click on the refreshed process. The earlier pointer
  interception by a `#window-container` `<details>` layer is not currently a
  stable repro, so it remains an observed transient rather than a fixed root
  cause.
- The operator-manifest layer is now codified on disk:
  - [FRIDAYS_OPERATOR_HEURISTICS.md](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/docs/architecture/FRIDAYS_OPERATOR_HEURISTICS.md)
  - [SYNC_STORY_SPEC.md](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/docs/architecture/SYNC_STORY_SPEC.md)
- These documents formalize:
  - `No state without story`
  - `Visible causality`
  - operator cognition as telemetry
  - the three-path evaluation model (`Standard`, `Compositional`, `Pivot`)
  - sync events as first-class Studio/Vortex narrative objects
- DOES/DEOS are now explicitly tied to the operator surface:
  - DOES = structural truth
  - DEOS = operational continuity
  - operator heuristics = visible causality / anti-dead-panel law
- The first live Sync Story proof-of-concept now exists in the real Vortex Git
  seam rather than only in architecture docs:
  - `core/time_machine.py::_vortex_maybe_git_sync()` now builds a structured
    Sync Story whenever a Vortex-managed Git batch is blocked, committed-only,
    or successfully pushed
  - the story includes:
    - origin (`source_node`, remote/transport, actor, trigger)
    - intent (branch, from/to SHA, threshold, change count)
    - transition (changed paths, categories)
    - consequence (result, push state, restart recommendation, next step)
    - intervention recommendations
    - risk classification (`safe`, `review-recommended`,
      `runtime-impacting`, `blocked`)
  - the proof-of-concept emits into existing live surfaces instead of creating a
    new parallel subsystem:
    - `core.spine` durable trace mirror
    - `swarm_bus` topic `git.sync`
    - `activity_log`
    - `ghost_circle`
  - node identity is resolved through `core.hive.local_node`, so the story is
    already naming real local nodes instead of generic “localhost” sludge
- This is intentionally phase 1 only:
  - it narrates the current Vortex Git batch path
  - it does not yet render a dedicated Studio sync card
  - it does not yet orchestrate cross-potato pull/apply flows
  - it gives the transport bridge a living event contract before the topology
    split lands
- Regression fence added for the Sync Story proof:
  - `tests/test_vortex_heartbeat_git_guard.py` now verifies blocked and
    runtime-impacting sync stories, not just raw commit/push behavior

---

## DEOS Execution Block

### Current Loudest Friction

- `WIN-018` is still the loudest operational friction on the Windows side:
  the agent/runtime surface is not trustworthy yet because:
  - local Ollama-backed agents are unavailable when Ollama is down
  - `nine` is returning upstream `403`
  - the Windows control plane therefore still lacks a reliable live-model path

### Executable Next Sequence

1. **Reveal Sync Story in Studio**
- **Intent:** complete the first visible-causality loop by surfacing the
  backend `git.sync` story that already exists.
- **Code seam:**
  - backend feed: `frontend/blueprints/spine_bp.py`
  - event stream/client: `frontend/static/js/core/trace-bus.js`
  - likely render targets: `frontend/static/js/views/traced.js`,
    `frontend/static/js/views/monitor.js`, or a small dedicated Studio stream
- **Deliverable:** lightweight Sync Stream / timeline card showing:
  - origin
  - branch/SHA movement
  - transition categories
  - risk
  - consequence
  - intervention
- **Exit criteria:** a real sync event can be triggered and visibly inspected in
  Studio without reading raw DB tables or server logs.
- **Tests:**
  - Python route/API tests for any new feed adapter
  - browser click/smoke validation that the stream renders and does not break
    Trace/Monitor

**May 29, 2026 - DEOS reveal layer made real in Traced**
- Landed the first Studio-visible Sync Stream directly in the live frontend
  surface instead of a sidecar component tree.
- Implemented in:
  - [frontend/static/js/views/traced.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/views/traced.js)
  - [frontend/static/css/trace.css](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/css/trace.css)
- What changed:
  - `Traced` now exposes a `sync_story` filter alongside the normal spine kinds
  - Sync Story events render as dedicated timeline rows instead of generic JSON
  - selecting a sync event now shows a readable causality card:
    - origin
    - intent
    - consequence
    - impact summary
    - intervention
    - raw event payload behind a `<details>` foldout
- This uses the existing spine feed and `time_machine.sync` events rather than
  inventing another transport or another persistence path.
- Regression fence added in:
  - [tests/test_spine.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_spine.py)
  - new test confirms a Sync Story payload round-trips through the trace log
    with the structure the UI now depends on
- Verification run:
  - `./.venv/bin/python -m pytest -q -s tests/test_spine.py tests/test_vortex_heartbeat_git_guard.py`
  - result: green
- Added a dedicated live-browser validation harness:
  - [windows/ui_sync_story_smoke.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/ui_sync_story_smoke.py)
- What it proves:
  - inject a live `sync_story` event through `/api/spine/log`
  - open `Traced`
  - filter `sync_story`
  - verify the row appears without manual refresh
  - click the row and verify the causality card sections render
  - verify the risk badge class/text matches the payload
- Live smoke run:
  - `LD_LIBRARY_PATH=.cache/local-libs/root/usr/lib/x86_64-linux-gnu ./.venv/bin/python windows/ui_sync_story_smoke.py`
  - result: green
  - artifact:
    - [sync-story-smoke-report.json](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/artifacts/sync-story-smoke-report.json)
    - [sync-story-smoke.png](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/artifacts/sync-story-smoke.png)
- Remaining gap for this phase:
  - the Sync Story is visible in `Traced`
  - it is not yet mirrored into a dedicated compact Monitor/Studio summary card
  - the dedicated live browser validation now exists and passes
  - broader Monitor/home-surface mirroring still remains

2. **Restore Real Windows Agent Truth**
- **Intent:** remove the loudest operational lie before broader architecture
  changes.
- **Code seam:**
  - `frontend/blueprints/chat.py`
  - `frontend/blueprints/agents.py`
  - `frontend/services/identity.py`
  - whichever provider path is causing `nine` to hit `403`
- **Deliverable:** Windows-facing/browser runtime can:
  - detect Ollama availability honestly
  - execute at least one known-good local model path when Ollama is up
  - execute `nine` cleanly or degrade with a truthful contract the UI can act on
- **Exit criteria:** Chat and Agents tiles reflect reality and at least one
  working model path is benchmarkable from the Windows-facing runtime.
- **Tests:**
  - targeted pytest for runtime/reachability contracts
  - browser smoke on Chat and Agents tiles
  - response-time capture for warm/cold model runs

3. **Only Then Add Governor Advisory Layer**
- **Intent:** impose law without freezing legacy paths prematurely.
- **Code seam:**
  - new `core/system_governor.py` or similar
  - first enforcement targets: sync/checkpoint/proposal transitions
- **Deliverable:** advisory validation of story completeness plus violation
  emission; not a universal hard blocker yet.
- **Exit criteria:** governance layer reports missing-story events without
  breaking stable flows.
- **Tests:**
  - unit tests for story validation
  - non-regression tests proving legacy paths still run

**May 29, 2026 - DEOS+ advisory governor integrated into real boot path**
- Implemented the advisory governor in:
  - [core/system_governor.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/core/system_governor.py)
- Wired it into the actual runtime seams, not an imaginary launcher/runtime:
  - [frontend/terminal.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/terminal.py)
  - [windows/launcher.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/launcher.py)
- Exposed runtime/API surfaces for governor state and focus updates:
  - [frontend/blueprints/governor_bp.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/governor_bp.py)
- Added focus-surface capture in the live frontend shell:
  - [frontend/static/js/core/aig_focus.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/core/aig_focus.js)
  - included from [terminal_base.html](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/templates/terminal_base.html)
- Current DEOS+ behavior:
  - boot initializes an advisory `SovereignGovernor`
  - focus-surface events publish as:
    - `swarm_bus` topic `focus.surface`
    - spine `system` events with payload kind `focus_surface`
  - advisory violations publish as:
    - `swarm_bus` topic `governor.violation`
    - spine warning events with payload kind `governor_violation`
    - `activity_log`
    - `ghost_circle`
  - storyless mutating actions trigger `NGAS` violation notices
  - padded / people-pleasing language triggers `DGIF` violation notices
- Intentional limit:
  - this does not hard-block runtime actions yet
  - it is an advisory enforcement layer while Windows/runtime stabilization is
    still active
  - the abusive fallback phrasing proposed in chat was not implemented; the
    governor stays direct and diagnostic without becoming a childish insult bot
- Verification run:
  - `./.venv/bin/python -m py_compile core/system_governor.py frontend/blueprints/governor_bp.py frontend/terminal.py windows/launcher.py tests/test_system_governor.py`
  - `./.venv/bin/python -m pytest -q -s tests/test_system_governor.py`
  - result: green

**May 29, 2026 - WIN-018 auth/runtime seam clarified and hardened**
- There is no `auth_handler.py` in this repo. The real Windows-facing Nine auth
  seam is:
  - [agents/nine/nine_agent.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/agents/nine/nine_agent.py)
  - [frontend/blueprints/nine.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/nine.py)
  - chat-side runtime handling in
    [frontend/blueprints/chat.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/chat.py)
- Probed Groq with the configured key from `utils/config.py` and reproduced the
  live failure directly:
  - `403 Access denied. Please check your network settings.`
- Hardened Nine/Groq handling:
  - added explicit 403/Access Denied classification in `nine_agent.py`
  - `/api/nine` and `/api/nine/stream` now return a classified runtime fault
    message instead of a raw generic exception blob
  - chat-side auto-offline logic now treats 403/access-denied/network-settings
    text as a runtime/auth failure, not just 401-style auth failures
- Verification run:
  - `./.venv/bin/python -m py_compile agents/nine/nine_agent.py frontend/blueprints/nine.py frontend/blueprints/chat.py tests/test_nine_runtime_faults.py`
  - `./.venv/bin/python -m pytest -q -s tests/test_nine_runtime_faults.py`
  - result: green

**May 29, 2026 - WIN-018 local sovereign path hardened**
- Followed the local branch instead of the external Groq branch.
- The honest-failure contract now exists for Ollama/runtime surfaces:
  - [core/ollama_runtime.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/core/ollama_runtime.py)
  - [core/model_runtime_gateway.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/core/model_runtime_gateway.py)
  - [frontend/blueprints/ollama.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/ollama.py)
- What changed:
  - low-level Ollama unreachability now classifies as:
    - `RUNTIME_OFFLINE`
  - protocol garbage from Ollama now classifies as:
    - `RUNTIME_PROTOCOL_ERROR`
  - `/api/ollama/models` now exposes `error_code` instead of only a generic
    error string when the backend is unreachable
  - `ollama_health()` now exposes `error_code='RUNTIME_OFFLINE'` when the
    runtime is down
  - Ollama runtime state transitions now emit into the system nervous system:
    - `swarm_bus` topic `runtime.ollama`
    - spine `system` events
- This means the local branch now fails explicitly instead of drifting into:
  - generic `500`
  - vague empty model state
  - no causal event trail
- Verification run:
  - `./.venv/bin/python -m py_compile core/ollama_runtime.py core/model_runtime_gateway.py frontend/blueprints/ollama.py tests/test_ollama_models_contract.py tests/test_runtime_health_badges.py`
  - `./.venv/bin/python -m pytest -q -s tests/test_ollama_models_contract.py tests/test_runtime_health_badges.py`
  - result: green

### Why This Order

- Sync Story backend already exists, so revealing it is low-risk and closes the
  visible-causality loop quickly.
- A hard governor before Windows agent truth is fixed would create clean theory
  over dirty runtime reality.
- Native Windows/Linux repo split remains deferred until browser/runtime truth is
  stable and visible.

**May 29, 2026 - Full-Zoo Ping executed and persisted**
- Added a real runtime census layer to the sovereign registry seam instead of
  inventing another manifest:
  - [utils/db/registry.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/db/registry.py)
  - [utils/db/_schema.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/db/_schema.py)
- New `agents` runtime-truth fields are now persisted:
  - `provider`
  - `fault_domain`
  - `runtime_status`
  - `runtime_reason`
  - `registry_status`
  - `runtime_checked_at`
- New executable seam:
  - `full_zoo_ping()`
  - probes local tier and paid tier
  - updates DB truth-state
  - emits `swarm_bus` topic `registry.zoo_ping`
  - emits a spine `system` event summarising orphan count
- Local-tier logic:
  - Ollama-backed locals classify as `LOADED`, `READY`, or `FAULT`
  - non-Ollama locals are no longer falsely blamed on Ollama outages
- Paid-tier logic:
  - identity pings classify provider/API faults explicitly
  - canonical provider mapping now overrides stale legacy tier drift
- Regression coverage added:
  - [tests/test_registry_full_zoo_ping.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_registry_full_zoo_ping.py)
  - plus existing routable fence:
    [tests/test_registry_routable.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_registry_routable.py)
- Verification run:
  - `./.venv/bin/python -m py_compile utils/db/registry.py utils/db/_schema.py tests/test_registry_full_zoo_ping.py`
  - `./.venv/bin/python -m pytest -q -s tests/test_registry_full_zoo_ping.py tests/test_registry_routable.py`
  - result: green
- Live census executed against the real DB:
  - `./.venv/bin/python - <<'PY' ... full_zoo_ping() ... PY`
  - summary at `2026-05-28T18:53:43Z`:
    - `agents_checked=17`
    - `active=1`
    - `disabled=2`
    - `orphaned=14`
- Reality snapshot:
  - `seven` survived as `ACTIVE` / `READY` because it is `LOCAL_RUNTIME`, not
    Ollama-backed
  - Ollama branch is still down, so Ollama-backed locals are orphaned on the
    current node
  - Groq (`nine`) is orphaned with live `403 Access denied`
  - GitHub (`ten`) is orphaned with `401 Bad credentials`
  - Hugging Face (`thirteen`) is orphaned with expired token
  - Anthropic (`twelve`) is orphaned due missing key
  - xAI (`eleven`) is orphaned due missing key
  - service/human rows are now explicitly persisted as `OUT_OF_SCOPE`, not
    folded into the paid/local availability census

**May 29, 2026 - Zoo Census surfaced in Monitor**
- Took the persisted census out of the DB cave and surfaced it in the live
  operator view.
- Added snapshot + trigger API:
  - [frontend/blueprints/agents.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/agents.py)
    - `GET /api/agents/zoo-ping` → persisted snapshot
    - `POST /api/agents/zoo-ping` → execute Full-Zoo Ping immediately
- Folded the latest census into the existing Monitor payload:
  - [frontend/blueprints/system.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/system.py)
    - `/api/monitor` now includes `zoo_census`
- Rendered a Monitor card with a manual trigger:
  - [frontend/static/js/views/monitor.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/views/monitor.js)
  - visible surface:
    - `Sovereign Zoo Census`
    - counts for checked / active / disabled / orphaned
    - last census timestamp
    - top orphan list
    - `Ping cages` action button
- This keeps the fun part honest:
  - button does real work
  - card reflects persisted truth
  - no decorative fake status
- Verification run:
  - `./.venv/bin/python -m py_compile utils/db/registry.py frontend/blueprints/agents.py frontend/blueprints/system.py tests/test_agents_zoo_ping_api.py`
  - `./.venv/bin/python -m pytest -q -s tests/test_agents_zoo_ping_api.py tests/test_registry_full_zoo_ping.py tests/test_registry_routable.py`
  - result: green

**May 29, 2026 - Zoo Census iteration: why, not just how many**
- Enriched the persisted zoo snapshot in
  [utils/db/registry.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/db/registry.py)
  so the operator surface can render actual fault structure instead of just
  a headcount.
- New snapshot fields:
  - `breakdown.active`
  - `breakdown.disabled`
  - `breakdown.local_faults`
  - `breakdown.paid_faults`
  - `top_reasons`
- Monitor card now shows:
  - survivors
  - local-vs-paid fault split
  - top fault reasons
  - still keeps the manual `Ping cages` trigger
- Current persisted truth from the richer snapshot:
  - only survivor: `seven`
  - local faults: `7`
  - paid faults: `7`
  - dominant failure reason:
    - Ollama unreachable (`7` agents)
- Verification run:
  - `./.venv/bin/python -m py_compile utils/db/registry.py tests/test_agents_zoo_ping_api.py`
  - `./.venv/bin/python -m pytest -q -s tests/test_agents_zoo_ping_api.py tests/test_registry_full_zoo_ping.py tests/test_registry_routable.py`
  - result: green

**May 29, 2026 - Live bug hunt: Monitor + full tile sweep**
- Ran the new targeted browser smoke for the Monitor zoo census:
  - [windows/ui_monitor_zoo_smoke.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/ui_monitor_zoo_smoke.py)
- First live failure was not product logic; it exposed a stale 5050 runtime:
  - live `GET/POST /api/agents/zoo-ping` returned `405`
  - app factory route map proved the code was correct (`GET/POST`)
  - conclusion: the running process had the wrong route map loaded
- Restarted the live runtime and revalidated:
  - fresh runtime now serves:
    - `GET /api/agents/zoo-ping` → `200`
    - `POST /api/agents/zoo-ping` → `200`
  - Monitor zoo smoke now passes end-to-end on the live runtime
  - artifact:
    - [monitor-zoo-smoke-report.json](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/artifacts/monitor-zoo-smoke-report.json)
- Re-ran the broad click sweep on the fresh runtime:
  - [windows/ui_surface_exhaustive.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/ui_surface_exhaustive.py)
  - artifact:
    - [ui-surface-exhaustive-report.json](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/artifacts/ui-surface-exhaustive-report.json)
- Clean harness defect fixed:
  - `Ping cages` was being misclassified as window chrome because `Ping`
    matched the old `Pin` regex
  - tightened `WINDOW_CHROME_RE`
  - added skip noise for global nav labels like `Open Spotlight` / `Open digest`
- Real remaining surface findings from the fresh sweep:
  - many interior controls still time out in-place rather than click cleanly:
    - `chat`
    - `knowledge`
    - `monitor`
    - `trace`
    - `studio`
    - `potato-farm`
    - `media-center`
    - `email`
    - `feeds`
    - `money-hub`
  - this no longer looks like dead endpoints; it looks like a mixture of:
    - overlay/stacking issues
    - non-actionable buttons in crowded control strips
    - still-noisy harness targeting for tile-internal controls

**May 29, 2026 - Exhaustive click harness made materially truthful**
- Kept iterating on the live browser sweep instead of treating the first report
  as truth.
- Fixed two real harness defects in
  [windows/ui_surface_exhaustive.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/ui_surface_exhaustive.py):
  - switched the click walk from a giant union locator to concrete element
    handles so Playwright stops timing out on the selector abstraction itself
  - added transient overlay/window cleanup between clicks so one tile cannot
    poison the rest of the run
- Explicitly clears:
  - `kn-info-modal`
  - `spotlight-overlay`
  - time-wizard/help modals
  - terminal shortcut modal
  - stray child windows opened by the click pass
- Result after rerun:
  - `monitor`, `trace`, `studio`, `time-wizard`, `potato-farm`,
    `media-center`, `email`, `feeds`, and `money-hub` now click far more
    cleanly in the broad pass
  - remaining survivors are much narrower and look real:
    - chat rail / rename controls are physically obstructed
    - some knowledge actions spawn tasker-related overlap
    - agents/access still have follow-on child-window interference
    - VPN surface no longer hard-fails the browser, but still degrades because
      Tailscale is absent on this node
- Verification runs:
  - `LD_LIBRARY_PATH=.cache/local-libs/root/usr/lib/x86_64-linux-gnu ./.venv/bin/python windows/ui_surface_exhaustive.py`
  - result: report still red, but now because of specific survivor bugs rather
    than harness contamination

**May 29, 2026 - VPN surface downgraded from hard-fail to explicit degraded state**
- Fixed the VPN/Tailscale route contract in
  [frontend/blueprints/vpn_bp.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/vpn_bp.py).
- Old behavior:
  - `/api/vpn/status` returned `503`
  - broad sweeps recorded console/resource errors in both Vortex and Access
- New behavior:
  - `/api/vpn/status` now returns `200` with explicit degraded shape when
    Tailscale is absent:
    - `ok=false`
    - `available=false`
    - `backend_state='unavailable'`
    - `error_code='VPN_UNAVAILABLE'`
- Added regression coverage:
  - [tests/test_vpn_status_contract.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_vpn_status_contract.py)
- Live verification after runtime restart:
  - `curl http://127.0.0.1:5050/api/vpn/status`
  - Vortex/Access browser probe showed no `4xx/5xx` resource failures while
    opening the VPN surface
- Why:
  - missing optional Tailscale runtime should degrade honestly, not poison the
    browser with a transport-level failure

**May 30, 2026 - Chat thread rail ghost hit-targets removed**
- Took `WIN-023` directly on the live chat surface rather than relying on the
  broad sweep report.
- Root cause:
  - the thread rail is collapsed by default, but its descendant controls were
    still effectively present as hidden hit-targets under the main chat pane
  - the sweep then "found" `Collapse thread rail` / `Rename thread` in a state
    where the rail should have been non-interactive
- Fixed in:
  - [frontend/static/css/views/chat.css](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/css/views/chat.css)
- CSS change:
  - collapsed rail now becomes genuinely non-interactive:
    - `visibility:hidden`
    - `pointer-events:none`
    - descendant controls inherit the same hidden/non-interactive state
  - thread resizer is also zeroed and non-interactive while the rail is
    collapsed
- Live browser proof:
  - collapsed state:
    - collapse button hidden
    - rename button hidden
    - restore button visible
  - expanded state:
    - rail width restored to `280`
    - collapse button clickable
    - rename button clickable
- Why:
  - collapsed UI must not leave ghost controls underneath the active surface;
    that is exactly how a living control plane turns back into fake click
    coverage and state confusion

**May 30, 2026 - Knowledge tab-bar overflow fixed**
- Took `WIN-024` on the live Knowledge surface instead of trusting the broad
  sweep's mixed follow-on window noise.
- Root cause:
  - the `kn-info-btn` ("What is the Knowledge Center?") was being pushed off
    the east edge of the Knowledge window by the tab strip layout
  - the button existed, but its hit-target was physically outside the window
- Fixed in:
  - [frontend/static/js/views/knowledge.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/views/knowledge.js)
- Layout change:
  - Knowledge tab bar now wraps cleanly
  - info button is fixed as `flex:0 0 auto` instead of being shoved off-canvas
- Live browser proof:
  - button now renders inside the Knowledge window bounds
  - clicking it opens `#kn-info-modal`
- Why:
  - this was not a data or API bug; it was a physical layout failure that made
    a real control unreachable

**May 30, 2026 - Fresh exhaustive pass after chat + knowledge + onboarding fixes**
- Re-ran:
  - `LD_LIBRARY_PATH=.cache/local-libs/root/usr/lib/x86_64-linux-gnu ./.venv/bin/python windows/ui_surface_exhaustive.py`
- New pass confirms the browser-first estate is materially cleaner now.
- Major clean surfaces in the latest report:
  - `monitor`
  - `trace`
  - `studio`
  - `time-wizard`
  - `access`
  - `potato-farm`
  - `email`
  - `feeds`
  - `money-hub`
- Narrow remaining survivors:
  - chat:
    - right-dock collapse control still collides with topbar/thread selector
  - knowledge:
    - `Go to workspace root` can still be intercepted after Tasker opens
    - one follow-on action still reports self-intercept from `win-knowledge`
  - agents:
    - explicit Enrollment click still opens `win-onboarding`, which then
      correctly becomes the active child window and can block subsequent tab
      clicks during the same sweep
  - media-center:
    - one unstable control still fails `scroll_into_view_if_needed`
- Important reduction:
  - stray `win-onboarding` no longer appears on fresh load by default
  - `What is the Knowledge Center?` is now a clean click
  - chat rail ghost controls are gone


