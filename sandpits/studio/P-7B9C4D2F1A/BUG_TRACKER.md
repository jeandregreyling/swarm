# Browser-First Runtime Stabilization Bug Tracker

Project: `P-7B9C4D2F1A`

## Open

- `WIN-001` Startup emits intermittent SQLite `database is locked` warnings during Windows runtime boot.
- `WIN-002` Repeated failed Windows launches can leave stale listeners on `127.0.0.1:5050`.
- `WIN-003` `pywebview` fails on WSL-backed repo paths and must not be treated as a required runtime.
- `WIN-004` Some modules still assume repo-local `swarm_memory.db` instead of `SWARM_DB_PATH`.
- `WIN-005` WSL-to-Windows localhost forwarding is inconsistent on this Dell, so Linux-side curl checks are misleading.
- `WIN-008` Windows startup latency is still variable; a clean listener can take several seconds to appear after launch.
- `WIN-011` Browser-first smoke runs still hit the auth overlay when no active session exists, so UI automation must remove it before pointer events reach Tasker.
- `WIN-012` Seven focus endpoints can hang or fail under Windows browser load when tiles request contextual project reasoning (`/api/seven/explain`, `/api/seven/observe`, `/api/seven/decide`).
- `WIN-013` Media Center bottom dock tabs are visibly unclickable on Windows because surrounding panels intercept pointer events before the tab buttons receive the click.
- `WIN-014` Monitor/diamond runtime still logs `psutil.sensors_temperatures` attribute failures on Windows during normal tile loads.
- `SAM-001` Samsung/Potato browser-first route still needs a fresh smoke audit on the current build.
- `XPLAT-001` `/api/ollama/models` returns hard `500` when Ollama is offline/refusing connections, which pollutes multiple browser surfaces that should degrade gracefully.
- `XPLAT-002` `/api/git/status?check_remote=1` can hang or `500` because the request path triggers interactive SSH host authenticity prompts against `github.com`.
- `XPLAT-003` Tasker "Run now" still surfaced a backend `500` for an existing task during browser smoke, even though the surrounding Tasker UI flow completed.
- `HARNESS-001` The new exhaustive tile click harness still captures shared/window-chrome controls too early on some tiles, so selector narrowing is required before it counts as true per-surface exhaustive coverage.
- `UI-001` After backend cleanup, the remaining broad-sweep failures are mostly tile-local clickability/intercept problems or state/content issues rather than route poison. These need to be worked surface-by-surface now.
- `ARCH-001` Windows Fridays still depends operationally on a WSL-backed repo path instead of a native Windows clone, which blocks the intended potato split and keeps filesystem semantics clunky.
- `ARCH-002` The shared Ollama model store on the NTFS drive has not yet been validated end-to-end from the Windows runtime/agent path, so model availability on Windows remains assumed rather than proven.
- `ARCH-003` Studio Git and Vortex ownership boundaries were previously implicit; the split is now agreed but still needs implementation fences so Vortex does not drift into acting like a second repo owner.
- `ARCH-006` Sync Story now exists at the backend event layer, but Studio does not yet render it as a first-class sync card. The transport is narrating itself; the operator surface is still catching up.
- `ARCH-008` DEOS+ / sovereign-governor policy was previously a chat-only idea with no runtime seam.
- `WIN-018` Windows/Chat agent selection is still operationally blocked by real runtime availability, not just UI polish:
  - Ollama runtime is down, so local chat agents return fast unreachable messages
  - `nine` currently returns upstream `403 Access denied`
  - service-tier agents like `scholar` are not directly routable from `/api/chat`
- `WIN-019` A broad browser probe saw the Chat home tile click intercepted once by a `#window-container` `<details>` subtree before runtime restart. The issue did not reproduce after restart, so it remains a transient layout/state bug pending a stable repro.
- `HARNESS-003` Exhaustive click harness still let one transient overlay or
  child window contaminate the rest of the run.
  - Fixed in the harness, but the tracker stays open until the new pass is the
    normal trustworthy baseline for future sweeps.
  - Current shape:
    - concrete element handles instead of union-locator clicks
    - transient overlay cleanup between clicks
    - stray child-window cleanup while preserving the active tile
- `WIN-024` Knowledge still has follow-on overlap problems after secondary
  actions spawn additional surfaces.
  - `+ Add` now clicks successfully in the broad pass.
  - `What is the Knowledge Center?` is fixed:
    - tab-bar now wraps correctly
    - info button stays inside window bounds
    - button opens `#kn-info-modal` on the live surface
  - Remaining survivor:
    - later actions can still be intercepted by the spawned Tasker window
- `WIN-025` Access and Agents still have child-window interference after
  opening secondary panels.
  - Access is largely clean now after VPN degradation + cleanup.
  - Remaining survivor is now concentrated in Agents:
    - explicit Enrollment click opens `win-onboarding`
    - subsequent tab clicks in the same sweep can then be intercepted by the
      active onboarding child window
- `WIN-027` Chat right-dock collapse controls still have topbar overlap in the
  latest truthful sweep.
  - Surviving controls:
    - `Collapse right dock`
    - one adjacent topbar utility control
- `WIN-028` Media Center still has one unstable control that fails
  `scroll_into_view_if_needed` in the broad pass.
- `WIN-025` Access and Agents still have child-window interference after
  opening secondary panels.
  - Access survivor now points at `win-vpn`
  - Agents survivors now point at `win-onboarding`

## Closed

- `WIN-000` No usable WSL-safe Windows start path.
  - Fixed by `windows/run-fridays-from-wsl.sh` plus first-run auto-install in `windows/start-fridays.bat`.
- `WIN-007` Windows Hive path still used repo-default DB locations.
  - Fixed by exporting `SWARM_MEMORY_DB` and `SWARM_HIVE_DB` into `%LOCALAPPDATA%\\Fridays`.
- `WIN-006` `/api/hive/nodes` timed out on Dell Windows browser runtime.
  - Cleared after fixing duplicate listener buildup on `5050` and validating the route against a single clean runtime.
- `WIN-009` Repeated `start` calls could spawn duplicate Windows runtimes on `5050`.
  - Fixed by making `windows/start-fridays.bat` reuse an existing healthy runtime instead of launching another process.
- `WIN-010` Browser shell background Git status checks returned `500` on Windows browser runs.
  - Fixed by making `frontend/blueprints/git.py` pass the active repo path as a per-command `safe.directory` value, avoiding UNC-path trust mismatches between `wsl$` and `wsl.localhost`.
- `WIN-015` Studio/Access/Vortex Git panels returned hard `500`s when `dev` worktree paths existed but were not real repos on Windows.
  - Fixed by downgrading those non-prod Git environment failures to handled `200` responses with `available=false`, so the browser surfaces stop throwing console/network errors.
- `WIN-016` App Center project listing could hard-fail with SQLite `database is locked` on Windows browser sweeps.
  - Fixed by moving `frontend/blueprints/app_center.py` onto `SWARM_DB_PATH` and adding SQLite WAL + busy-timeout handling.
- `WIN-017` Windows/browser hardening had no regression fence for the new handled Git-unavailable path or the Windows-only Hive DB fallback.
  - Fixed by adding focused tests in `tests/test_git_branch_mirror.py` and `tests/test_hive_blueprint.py`, then re-running the targeted Git/Hive Studio slice in the repo `.venv`.
- `XPLAT-001` `/api/ollama/models` returned hard `500` when Ollama was offline/refusing connections.
  - Fixed by degrading `frontend/blueprints/ollama.py` to return `200` with `ok=false`, `running=false`, and an empty model list.
- `XPLAT-002` `/api/git/status?check_remote=1` could hang or `500` because browser requests triggered interactive SSH prompts.
  - Fixed by making remote fetches non-interactive and fail-soft in `frontend/blueprints/git.py`.
- `XPLAT-003` Tasker "Run now" looked like a backend failure during browser smoke.
  - Cleared after fixing the smoke harness to use an OS-appropriate shell command instead of forcing a Windows payload into a Linux-hosted runtime.
- `HARNESS-001` The exhaustive tile click harness captured shared/window-chrome controls too early.
  - Partially fixed by correctly scoping selectors to the active tile and skipping shared window chrome first; remaining failures now look like real tile interaction problems rather than harness cross-talk.
- `WIN-020` Local agent status feeds previously lied when Ollama was offline.
  - Fixed by restoring runtime-aware reachability checks so local agents report
    `offline` in `/api/agents/config` and `down` in `/api/agents/status`
    whenever the local Ollama runtime is unavailable.
- `ARCH-004` Ghost-circle thought logging for human prompts had gone stale.
  - Fixed by restoring append-only `ghost_circle` writes for human chat turns,
    with owner-session alias attribution resolving back to `jeandre` instead of
    anonymous `ghost`.
- `ARCH-005` Fridays had no codified operator heuristic layer on disk, which
  left the anti-dead-panel philosophy trapped in chat and prone to drift.
  - Fixed by adding:
    - [FRIDAYS_OPERATOR_HEURISTICS.md](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/docs/architecture/FRIDAYS_OPERATOR_HEURISTICS.md)
    - [SYNC_STORY_SPEC.md](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/docs/architecture/SYNC_STORY_SPEC.md)
  - `DOES_SOVEREIGN_NODE.md` now explicitly links structural truth to the new
    operator-facing visible-causality layer.
- `ARCH-007` Sync Story previously existed only as manifesto/spec text with no
  real execution seam in the codebase.
  - Fixed by wiring the first live proof-of-concept into
    `core/time_machine.py::_vortex_maybe_git_sync()`.
  - Vortex-managed Git batch events now emit a structured Sync Story with
    origin, intent, transition, consequence, intervention, node identity, and
    risk classification.
  - The story is mirrored through `core.spine`, `swarm_bus` topic `git.sync`,
    `activity_log`, and `ghost_circle`.
  - Regression coverage was added in
    `tests/test_vortex_heartbeat_git_guard.py`.
- `ARCH-006` Sync Story existed in backend event flow but was not visible in a
  readable operator surface.
  - Partially fixed by rendering Sync Story as a dedicated causality card in
    the `Traced` window:
    - sync-specific filter
    - sync-specific timeline row
    - readable detail card for origin / intent / consequence / impact /
      intervention
  - Implemented in:
    - [frontend/static/js/views/traced.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/views/traced.js)
    - [frontend/static/css/trace.css](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/css/trace.css)
  - Trace-log regression coverage added in
    [tests/test_spine.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_spine.py)
  - Live browser validation now exists and passes via:
    - [windows/ui_sync_story_smoke.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/ui_sync_story_smoke.py)
    - [sync-story-smoke-report.json](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/artifacts/sync-story-smoke-report.json)
  - Remaining work:
    - no compact Monitor summary yet
    - still not mirrored into a home/Monitor-level summary surface
- `ARCH-008` DEOS+ / sovereign-governor policy had no implementation seam.
  - Fixed in advisory form with:
    - [core/system_governor.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/core/system_governor.py)
    - [frontend/blueprints/governor_bp.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/governor_bp.py)
    - [frontend/static/js/core/aig_focus.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/core/aig_focus.js)
  - Boot integration now occurs in the real app factory:
    - [frontend/terminal.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/terminal.py)
    - [windows/launcher.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/launcher.py)
  - Focus-surface telemetry and governor violation notices are now live through
    `swarm_bus`, spine, `activity_log`, and `ghost_circle`.
  - Regression coverage added in
    [tests/test_system_governor.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_system_governor.py)
  - Remaining work:
    - governor is advisory only, not hard-blocking
    - AIG is currently focus-surface capture, not a full inference policy engine
- `WIN-018` Nine/Groq runtime fault classification was too vague and the
  supposed `auth_handler.py` target did not exist.
  - Partially fixed by hardening the real seam:
    - [agents/nine/nine_agent.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/agents/nine/nine_agent.py)
    - [frontend/blueprints/nine.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/nine.py)
    - [frontend/blueprints/chat.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/chat.py)
  - Groq 403s are now classified explicitly as:
    - access denied
    - likely network/proxy/firewall/account-policy fault
  - chat-side auto-offline logic now treats that 403 class as a runtime/auth
    failure and can take Nine offline instead of leaving it in a half-alive
    state.
  - Regression coverage added in
    [tests/test_nine_runtime_faults.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_nine_runtime_faults.py)
  - Remaining work:
    - actual external cause of Groq 403 still needs environmental remediation
      or account/policy correction
    - Ollama/local-model availability is still the louder branch of `WIN-018`
- `WIN-018` Local Ollama branch previously degraded without an explicit runtime
  fault code or event-level narrative.
  - Partially fixed in the real local-runtime seam:
    - [core/ollama_runtime.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/core/ollama_runtime.py)
    - [core/model_runtime_gateway.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/core/model_runtime_gateway.py)
    - [frontend/blueprints/ollama.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/ollama.py)
  - `RUNTIME_OFFLINE` is now the explicit contract for backend unreachability.
  - `ollama_health()` now emits runtime state transitions to:
    - `swarm_bus` topic `runtime.ollama`
    - spine system events
  - `/api/ollama/models` now returns `error_code` instead of only a raw error
    string when the backend is unreachable.
  - Regression coverage added in:
    - [tests/test_ollama_models_contract.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_ollama_models_contract.py)
    - [tests/test_runtime_health_badges.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_runtime_health_badges.py)
  - Remaining work:
    - the actual Windows/shared-runtime Ollama availability still needs live
      remediation and benchmark validation
    - one end-to-end successful local model path is still needed to close the
      sovereign loop
- `ARCH-009` Registry had no sovereign runtime census and no persisted
  truth-state for the zoo.
  - Fixed by adding a Full-Zoo Ping seam in:
    - [utils/db/registry.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/db/registry.py)
    - [utils/db/_schema.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/db/_schema.py)
  - New persisted fields on `agents`:
    - `provider`
    - `fault_domain`
    - `runtime_status`
    - `runtime_reason`
    - `registry_status`
    - `runtime_checked_at`
  - Full-Zoo Ping now:
    - probes local tier + paid tier
    - marks failed enabled agents as `STATUS_ORPHANED`
    - preserves explicit disables as `DISABLED`
    - emits `registry.zoo_ping` into `swarm_bus`
    - emits a spine `system` event with orphan summary
  - Regression coverage added in:
    - [tests/test_registry_full_zoo_ping.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_registry_full_zoo_ping.py)
  - Live census result (`2026-05-28T18:53:43Z`):
    - checked: `17`
    - active: `1`
    - disabled: `2`
    - orphaned: `14`
  - Current orphan causes from the real node:
    - Ollama branch offline / refused connection:
      `duck`, `eight`, `librarian`, `llama`, `qwen`, `sniffles`, `twenty`
      plus disabled locals `gemma`, `mistral`
    - Groq `nine`:
      `403 Access denied. Please check your network settings.`
    - GitHub `ten`:
      `401 Bad credentials`
    - Hugging Face `thirteen`:
      token expired
    - Anthropic `twelve`:
      missing key
    - xAI `eleven`:
      missing key
    - legacy DB drift:
      `ghost_coder`, `nineteen` remain unsupported external rows
  - Important correction:
    - `seven` is correctly classified as `LOCAL_RUNTIME` / `READY`
      during Ollama outages and is no longer falsely blamed on Ollama
    - `ghost`, `scholar`, `seeker`, and `duck_ddg` are now persisted as
      `OUT_OF_SCOPE` because the audit contract is local-tier + paid-tier only
- `ARCH-010` Full-Zoo Ping existed as backend truth but was still invisible to
  the operator unless manually invoked from shell.
  - Fixed by surfacing the census in the Monitor view and adding a manual
    trigger endpoint/button:
    - [frontend/blueprints/agents.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/agents.py)
    - [frontend/blueprints/system.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/system.py)
    - [frontend/static/js/views/monitor.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/views/monitor.js)
  - New operator-facing contract:
    - `GET /api/agents/zoo-ping` returns the persisted snapshot
    - `POST /api/agents/zoo-ping` runs the census immediately
    - `/api/monitor` now carries `zoo_census`
    - Monitor renders counts + top orphan names + `Ping cages`
  - Regression coverage added in:
    - [tests/test_agents_zoo_ping_api.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_agents_zoo_ping_api.py)
- `ARCH-011` Monitor Zoo Census v1 exposed counts but still made the operator
  mentally reconstruct the fault topology.
  - Improved by enriching the snapshot payload in
    [utils/db/registry.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/utils/db/registry.py)
    and rendering the added structure in
    [frontend/static/js/views/monitor.js](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/js/views/monitor.js)
  - New visible fields:
    - active survivors
    - local vs paid fault counts
    - top fault reasons
  - Current dominant reason remains:
    - Ollama unreachable across `7` local agents
- `WIN-021` Live 5050 runtime served a stale route map after the zoo census UI
  landed.
  - Observed symptom:
    - browser and `curl` both got `405 METHOD NOT ALLOWED` on
      `GET/POST /api/agents/zoo-ping`
    - `Allow: OPTIONS, DELETE`
  - Verified source code was correct by dumping the fresh app factory route map:
    - `/api/agents/zoo-ping ['GET', 'HEAD', 'OPTIONS', 'POST']`
  - Real issue:
    - stale running process, not bad route code
  - Action taken:
    - restarted the live `frontend/terminal.py` runtime
  - Post-restart result:
    - Monitor zoo smoke passed
    - `GET/POST /api/agents/zoo-ping` both return `200`
- `HARNESS-002` Exhaustive surface sweep misclassified `Ping cages` as window
  chrome.
  - Cause:
    - `Ping` matched the old `Pin` prefix regex
  - Fixed in:
    - [windows/ui_surface_exhaustive.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/ui_surface_exhaustive.py)
  - Also suppressed known harness-noise labels:
    - `Open Spotlight`
    - `Open digest`
- `WIN-022` Fresh-runtime full surface sweep still shows interior-control click
  failures across multiple tiles even after the stale route issue was cleared.
  - Current hot list from the fresh report:
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
  - Evidence:
    - [ui-surface-exhaustive-report.json](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/windows/artifacts/ui-surface-exhaustive-report.json)
  - Current interpretation:
    - no broad endpoint poisoning visible
    - remaining failures are now mostly control-level interaction/state issues
- `WIN-026` VPN/Tailscale surface poisoned browser sweeps with hard `503`
  failures when the optional runtime was absent.
  - Fixed by changing `/api/vpn/status` to degrade as `200` with:
    - `ok=false`
    - `available=false`
    - `backend_state='unavailable'`
    - `error_code='VPN_UNAVAILABLE'`
  - Implemented in:
    - [frontend/blueprints/vpn_bp.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/blueprints/vpn_bp.py)
  - Regression coverage added in:
    - [tests/test_vpn_status_contract.py](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/tests/test_vpn_status_contract.py)
  - Live verification:
    - `curl /api/vpn/status` now returns `200`
    - Vortex/Access VPN browser probe no longer records `4xx/5xx` resource
      failures when opening the degraded surface
- `WIN-029` Windows packaged/native app could present a cross-generation
  frontend/backend mix that looked like "agents vanished" even though the repo
  runtime was healthy.
  - Observed symptom cluster:
    - Agents tile errors
    - Services panel empty
    - Vortex error
    - VPN error
    - roster appeared to lose `duck`, `qwen`, and paid/API agents
  - Verified false lead:
    - fresh repo runtime returns `200` on `/api/agents/config`,
      `/api/agents/ops-summary`, `/api/services`, `/api/vpn/status`, and
      `/api/time/timeline`
    - source contract uses `/api/time/...` for Vortex, not `/api/vortex/...`
  - Real issue:
    - Windows app/runtime was not aligned with the repo runtime; stale or wrong
      runtime generation remained plausible even after restart
  - Mitigation:
    - runtime-id health guard committed in launcher/start path
    - packaged app remains untrusted until parity validation is complete
- `WIN-030` Windows-side `.venv-win` can exist in a false-good state with only
  `pip` installed, causing the launcher server thread to die before binding
  `5050`.
  - Observed failure:
    - `ModuleNotFoundError: No module named 'flask'`
    - thrown from `windows/launcher.py` server thread when importing
      `frontend/terminal.py`
  - Why this is worse than a clean install failure:
    - launcher can look present, but backend never comes up
    - operator then sees blank/broken Chrome and assumes route loss
  - Required fix:
    - bootstrap/install path must assert the full app dependency set, not just
      presence of `python.exe`
    - packaged/native launch needs a hard preflight for `flask` + core deps
      before claiming startup
- `WIN-023` Chat still has physical hit-target obstruction on thread-rail
  controls in the live browser surface.
  - Closed after fixing the collapsed-state contract in
    [frontend/static/css/views/chat.css](/mnt/wsl/PHYSICALDRIVE0p1/home/seven/swarm/frontend/static/css/views/chat.css):
    - collapsed rail now hides and disables descendant controls completely
    - collapsed rail resizer is also disabled
  - Live browser proof:
    - collapsed state: restore visible, collapse/rename hidden
    - expanded state: collapse and rename both clickable
