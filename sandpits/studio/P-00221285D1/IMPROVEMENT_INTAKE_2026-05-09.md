# P-00221285D1 Improvement Intake - 2026-05-09

Owner request: capture UI, Git, agent, Ollama, and Samsung tablet work so it is
not lost and can be handled through Studio instead of scattered chat.

## Grok Pot Visibility and Review Flow

Current state:

- Grok Pot intake exists at `sandpits/studio/grok_pot/`.
- Grok Pot Money Maker exists at `sandpits/studio/Grok-Pot-Money-Maker/`.
- Remote branch `origin/grok-pot-money-maker-p855e64250c` exists.
- Current local branch `grok-pot-money-maker-p855e64250c` has local Vortex
  heartbeat commits ahead of its remote, with no content diff in those commits.

Required behavior:

- Grok writes suggestions only.
- Human asks Codex/teacher to review, amend, or append.
- Reviewed changes move through PRs and Studio notes.
- Draft Grok text must stay in Grok Pot until reviewed.

How to see it today:

- File view: open `sandpits/studio/grok_pot/README.md`.
- File view: open `sandpits/studio/grok_pot/REVIEW_2026-05-09.md`.
- File view: open `sandpits/studio/Grok-Pot-Money-Maker/PROJECT_PLAN.md`.
- Git view: fetch remote branches and inspect `origin/grok-pot-*` branches.

Gap:

- Studio does not yet provide a clean Grok Pot project tile with remote branch
  preview, branch checkout, pull, and compare controls.

## Studio Git Remote Integration

Current state:

- Backend `/api/git/status?check_remote=1` can fetch origin and report
  ahead/behind drift.
- Git UI shows local changed files and diffs.
- Git UI has ALM proposal buttons for stage, unstage, commit, and Vortex
  snapshot.

Requested improvement:

- Connect Studio Git visibly to online GitHub state.
- Show remote branches, not only local working-tree changes.
- Add buttons for fetch, pull, checkout remote branch, compare branch, and open
  branch files.
- Let the user manually pull online branch work onto the Dell or another
  machine without terminal commands.
- Show which environment is being inspected: PROD, UAT, DEV, or feature branch.
- Make it obvious when local is behind, ahead, or on a branch with unpushed
  Vortex-only heartbeat commits.

Acceptance target:

- A non-coder can open Studio Git, see online Grok branches, inspect files, pull
  selected work locally, and ask for review without using the shell.

## Agent Tile Rework

Current problem:

- Agent tile layout is hard to scan.
- Columns/fields waste space and appear fixed-width.
- Add/change-agent screen relies too much on free text.
- It is too hard to assign a new model to a slot, such as using a DeepSeek
  model for agent 18.

Requested improvement:

- Replace free-text model fields with dropdowns.
- Dropdowns should refresh from available model inventories:
  - local Ollama installed models
  - currently loaded/running Ollama models
  - LM Studio models if available
  - configured cloud model providers where applicable
- Keep advanced free-text override behind an "Advanced" control.
- Rework layout for flexible columns and denser information.
- Add clear slots/roles so agent 18 can be assigned intentionally.

Local model check on 2026-05-09:

- Installed: `deepseek-r1:7b`.
- Not found in `ollama list`: DeepSeek 27B.
- Action needed: verify whether the expected 27B model was downloaded under a
  different tag, failed to pull, or exists outside this Ollama instance.

## Local AI Tab Rework

Current problem:

- Local AI tab is not useful enough as a control surface.
- It overlaps with Ollama display but does not feel like the place to manage
  runtime behavior.

Requested improvement:

- Turn Local AI into the control center for Ollama and watchdog.
- Show installed models, loaded models, model size, health, stuck/stopping
  state, and force-unload controls.
- Add watchdog settings and controls:
  - stale timeout thresholds
  - stuck job detection
  - force stop/rerun policy
  - Ollama runner reconciliation
- Add model pull/search workflow and clear install status.
- Surface missing expected models, including the DeepSeek 27B concern.

Existing useful pieces:

- `frontend/blueprints/ollama.py`
- `frontend/static/js/views/localai.js`
- `frontend/static/js/views/ollama.js`
- `docs/architecture/MODEL_RUNTIME_GATEWAY.md`
- `tests/test_runtime_health_badges.py`

## Samsung Tablet / Second Potato

Question:

- How far are we on using the Samsung tablet connected to the Dell for its small
  GPU and building the Android package as a second potato?

Current state found on 2026-05-09:

- Vision logged in `docs/HIVE_VISION.md`.
- Production plan logged in `docs/HIVE_PRODUCTION_PLAN.md`.
- Android/Termux telemetry provider exists:
  `core/hive/providers/android.py`.
- Termux install path exists:
  `ops/install/install_termux.sh`.
- Install routes and tests include Termux/core hive support:
  `tests/test_hive_install_routes.py`.
- Android provider tests exist:
  `tests/test_hive_android_provider.py`.
- APK file exists at `ops/install/android/swarm-hive.apk` and is an Android
  package.

Reality check:

- Termux-based Android node support is partially built.
- Real Android product flow is not complete.
- `docs/HIVE_PRODUCTION_PLAN.md` still lists Android Phase E as after desktop
  installer, mesh, discovery, packaging, and ops hardening.
- Android provider currently exposes `inference.cpu`; it does not yet expose or
  control tablet GPU/NPU compute.

Next review task:

- Verify whether `swarm-hive.apk` is a real usable current package or stale
  artifact.
- Run the hive install tests.
- Confirm whether the Samsung tablet can enrol over Termux today.
- Decide whether the next Android increment is Termux node reliability or real
  APK packaging.

## Priority Proposal

1. Studio Git remote branch browser and pull/checkout controls.
2. Agent tile model dropdowns backed by live Ollama inventory.
3. Local AI as Ollama/watchdog control center.
4. Samsung tablet status review and second-potato bring-up plan.
5. Grok Pot project tile with suggestion-only workflow and review gates.

## Logging Rule

Every increment from this intake should leave:

- a Git branch or PR,
- a Studio note under `sandpits/studio/`,
- validation output,
- and a clear "promoted / parked / rejected" decision.
