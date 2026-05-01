# Fan Controller Runbook

Cross-platform fan control helper for Seven's Swarm (Phase-4 B18).

## Scope

- `core/fan_controller.py` — read-only temperature monitor (safe, no root).
- `frontend/blueprints/fan.py` — `/api/fan/status` and `/api/fan/mode` endpoints.
- `ops/swarm-fanctl.py` — **opt-in** privileged helper that actually writes to
  `/sys/firmware/acpi/platform_profile` and `/sys/class/hwmon/*/pwmN_enable`.
- `ops/swarm-fanctl.service` — systemd unit for the helper.

## Modes

| Mode  | Intent | Target (CPU °C) |
| ----- | ------ | ---------------- |
| auto  | Normal desk use | 56–60 |
| boost | Heavy sustained work | ~40 |

Temperature targets are achieved by the helper through the platform profile
(`balanced` vs `performance`) and optional direct PWM writes on chips that
expose them in `/sys/class/hwmon`.

## Install (requires sudo — opt-in)

```bash
sudo cp ops/swarm-fanctl.py /usr/local/bin/swarm-fanctl
sudo chmod 755 /usr/local/bin/swarm-fanctl
sudo cp ops/swarm-fanctl.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now swarm-fanctl.service
```

To let the Swarm user talk to the socket without sudo, after the service
starts once look up the group owning `/run/swarm-fanctl.sock` and
`usermod -aG <group> seven`.

## Status without helper

Before the helper is installed, `/api/fan/status` still returns CPU temps read
directly from `/sys/class/hwmon`, and `/api/fan/mode` returns HTTP 503 with
`{ok:false, reason:"helper-not-installed"}`.

## Uninstall

```bash
sudo systemctl disable --now swarm-fanctl.service
sudo rm /etc/systemd/system/swarm-fanctl.service /usr/local/bin/swarm-fanctl
sudo systemctl daemon-reload
```

## Hardware notes

`_apply_mode()` is the hardware-specific bit. The default implementation:
- Tries `platform_profile` first (works on most modern Dell/Lenovo laptops and
  some Dell OptiPlex boards).
- Then attempts to set every `/sys/class/hwmon/*/pwmN_enable` to `1` and its
  paired `pwmN` to `255` when boost is requested.

If your machine ignores these (e.g. proprietary Dell EC), swap in `ipmitool` or
a vendor-specific binary by editing `_apply_mode()` — keep the socket protocol
identical so the Flask side needs no changes.
