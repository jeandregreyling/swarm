# Samsung Tablet / Second Potato — Review

**Reviewed:** 2026-05-17
**Source intake:** `sandpits/studio/P-00221285D1/IMPROVEMENT_INTAKE_2026-05-09.md`
**Scope:** Verify APK status, hive install path, tablet enrolment readiness, and
recommend the next Android increment.

---

## APK status: `ops/install/android/swarm-hive.apk`

- **Real package.** `file(1)` reports `Android package (APK), with gradle
  app-metadata.properties, with APK Signing Block`. 4.5 MB on disk.
- Built with the AndroidX stack (`androidx.activity`, `appcompat`, `cardview`,
  `coordinatorlayout`, `core-ktx`, `customview`, `cursoradapter`, …) and
  Kotlin coroutines (`DebugProbesKt.bin` present), so this is a real
  Compose/AppCompat app, not a stub.
- All archive entries dated `1981-01-01 01:01` — that is the Gradle deterministic
  / reproducible-build epoch, **not** a stale artifact. The on-disk mtime
  (2026-05-17) reflects when it was last rebuilt.
- Verdict: **current package, not stale.** It is, however, a *telemetry* package
  (see provider section below), not a compute worker.

## Hive install path

- `tests/test_hive_install_routes.py` + `tests/test_hive_android_provider.py`:
  **35/35 pass** as of this review.
- `ops/install/install_termux.sh` is fully wired: leader URL via env, optional
  `termux-services`/runit autostart, `nohup` fallback, idempotent re-run.
- Provider `core/hive/providers/android.py` reads `/proc/meminfo`, `/proc/cpuinfo`,
  `cpufreq` ratios, `getprop`, and (if `Termux:API` is installed) battery state.
  Capabilities list is exactly `['inference.cpu']`.

## Can the Samsung tablet enrol over Termux today?

**Yes, as a telemetry node.** Required steps on the tablet:

1. Install Termux + `Termux:API` from F-Droid (Play Store builds are stale).
2. `pkg install python git curl`.
3. `git clone <repo>` onto the tablet (or `scp` a worktree).
4. `SWARM_HIVE_LEADER=http://<dell-ip>:5050 ./ops/install/install_termux.sh`.

The node will appear on the hive dashboard and report CPU/RAM/battery
telemetry. It will **not** run inference for the leader because the
`inference.cpu` capability is advertised but no work-pull/runner code is wired
on the Termux side yet (the agent only POSTs telemetry samples).

## Reality check vs. intake

| Intake claim | Reviewed status |
|---|---|
| APK exists | ✅ real, signed, recent |
| Termux node support partially built | ✅ telemetry only |
| Provider exposes only `inference.cpu` | ✅ confirmed in code |
| No tablet GPU/NPU control | ✅ confirmed — no NNAPI / Vulkan compute path |
| Android Phase E is post-desktop installer | ✅ matches `docs/HIVE_PRODUCTION_PLAN.md` |

## Recommendation: next Android increment

**Prefer Termux node reliability over rebuilding the APK** for these reasons:

1. The APK today is a *control surface*, not a worker. Adding GPU compute
   inside the APK requires NNAPI / TFLite GPU / Vulkan compute integration —
   a substantial new project, not an increment.
2. Termux on aarch64 can run `ollama serve` natively (qwen2.5:0.5b /
   gemma2:2b class models fit on tablet RAM). A Termux worker is the
   shortest path to "tablet as second potato".
3. The hive install/test surface is already green. Building on it is
   cheap; building a new APK feature track is expensive.

Concrete next steps if we proceed with Termux-first:

- [ ] Extend `ops/hive_agent.py` (or sibling worker) to *receive* work, not
      just send telemetry. Add capability flag `inference.ollama` when
      `ollama` binary is on PATH.
- [ ] Document the Termux Ollama install in `docs/HIVE_VISION.md` so the
      Samsung tablet can be the first non-Dell node serving real prompts.
- [ ] Add an integration smoke test gated on `SWARM_TEST_TERMUX_NODE=1`.
- [ ] Revisit the APK only when there is a concrete UX need on-device
      (chat client, hot-spot leader, etc.).

## Open questions for the owner

1. Is the tablet always tethered/charged at the Dell, or expected to roam?
   (Affects whether we should bother with `Termux:Boot` autostart.)
2. Tablet RAM and chipset? (Determines which Ollama models are viable.)
3. Do we want the APK kept current as a control UI, or is the web Terminal
   sufficient when the tablet is on the same LAN?
