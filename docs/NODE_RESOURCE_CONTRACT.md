# Node Resource Contract — v0 (draft)

> Status: **Draft / RFC**. This is the API every Hive node speaks, regardless
> of OS. v0 is deliberately small. We grow it only when a real node needs a
> field, never speculatively.

## Purpose

A single JSON shape that any Fridays-enrolled device — Linux, Windows, macOS,
Android, iOS — can produce for telemetry and accept for policy. This is the
seam that lets Monitor render any node identically and lets the scheduler
pick "cheapest capable node" without per-platform branching in core logic.

## Wire format

JSON over the existing local channel (Unix socket on Linux, equivalent on
each platform). Versioned at the envelope.

### Telemetry (node → executive)

```json
{
  "contract": "node.resource/v0",
  "node_id": "seven-potato",
  "platform": "linux-mint",
  "ts": 1714723200,
  "compute": {
    "cpu_load_pct": 47,
    "cpu_peak_temp_c": 67,
    "cpu_throttled": false,
    "gpu_present": false,
    "gpu_load_pct": null,
    "gpu_temp_c": null,
    "npu_present": false
  },
  "thermal": {
    "fan_rpm": 1770,
    "fan_pwm": 128,
    "fan_max_rpm": 4000,
    "fan_mode": "auto",
    "controllable": true
  },
  "memory": {
    "ram_total_mb": 32000,
    "ram_free_mb": 14200,
    "swap_used_mb": 0
  },
  "power": {
    "on_battery": false,
    "battery_pct": null,
    "thermal_pressure": "nominal"
  },
  "capabilities": [
    "inference.cpu",
    "inference.ollama",
    "scheduler.coordinator"
  ]
}
```

### Policy (executive → node)

```json
{
  "contract": "node.policy/v0",
  "node_id": "seven-potato",
  "ts": 1714723200,
  "policy": {
    "thermal": {
      "fan_mode": "boost",
      "boost_exit_temp_c": 50
    },
    "compute": {
      "max_load_pct": 100,
      "accept_jobs": true
    }
  }
}
```

## Field rules

- Any field a platform cannot provide is `null`, never absent.
- `controllable: false` means telemetry-only — policy commands for that
  subsystem are accepted but no-op'd, and the executive must surface that.
- `capabilities` is a flat list of well-known strings. New strings are added
  to this doc when a node first emits them.
- `thermal_pressure` enum: `"nominal" | "fair" | "serious" | "critical"`.
  Mapped from native APIs (Linux thermal zones, iOS NSProcessInfo, Android
  PowerManager.getCurrentThermalStatus, macOS thermal pressure notifications).
- All temps in °C, all RPM as integers, all percentages 0–100 integer.

## Per-platform mapping (informative)

| Platform | fan_rpm source                  | fan_mode source             | thermal_pressure source                        |
| -------- | ------------------------------- | --------------------------- | ---------------------------------------------- |
| Linux    | hwmon (it87 / dell_smm)         | swarm-fanctl                | thermal_zone* / cpu throttle                   |
| Windows  | WMI MSAcpi_ThermalZoneTemp      | OEM SDK or libre_hardware   | WMI thermal namespace                          |
| macOS    | `powermetrics` / SMC            | n/a (SMC restricted)        | NSProcessInfo `thermalState`                   |
| Android  | sysfs `/sys/class/thermal`      | n/a (vendor-locked)         | `PowerManager.getCurrentThermalStatus`         |
| Samsung  | n/a (passive)                   | n/a (passive)               | Battery temp → derive_thermal_pressure         |
| iOS      | n/a                             | n/a                         | `NSProcessInfo.thermalState`                   |

### Samsung / Android capability detection

Samsung Galaxy devices (and modern Android tablets such as the S9-FE)
ship with NPUs that accelerate TFLite via NNAPI.  The Hive agent
(native APK and Termux paths) detects these capabilities at runtime:

- `inference.cpu` — always advertised.
- `inference.tflite` — always advertised (TFLite CPU delegate is
  universal on Android; NNAPI delegate activates when an NPU is
  present).
- `inference.gpu` — advertised when `ActivityManager` reports GLES 2.0+
  support (universal on modern devices).
- `inference.npu` — advertised when one of the following is true:
  - Samsung-specific Eden NN driver (`libeden_nn_onsystem.so`) is
    present in `/vendor/lib[64]` or `/system/lib[64]`.
  - The SoC fingerprint (`ro.hardware` / `ro.product.board`) matches a
    known NPU-capable chip (`exynos2100`, `exynos2200`, `exynos2400`,
    `sm8450`, `sm8550`, `sm8650`).
  - Generic NNAPI HAL (`libneuralnetworks.so`) is present.

The scheduler can therefore route TFLite/NPU jobs to Samsung nodes
without hard-coding a vendor list.

Mobile platforms emit `controllable: false` for `thermal` and accept policy
as advisory only — they self-throttle compute load instead.

## v0 scope (explicitly)

- Telemetry shape ✓
- Policy shape ✓
- One Linux node implementation (Y.58g, in flight)

## Out of v0

- Multi-node enrolment / discovery
- Job scheduling
- Auth / signed channel (placeholder — local socket only for v0)
- Cross-node compute donation

These get their own contracts as we get to them.

## Files

- Linux node implementation: [ops/swarm-fanctl.py](ops/swarm-fanctl.py)
- Read-only client: [core/fan_controller.py](core/fan_controller.py)
- HTTP surface: [frontend/blueprints/fan.py](frontend/blueprints/fan.py)

(The existing fanctl helper already produces a subset of this contract. Y.58g
will widen it to match v0 exactly so future platforms have a stable target.)
