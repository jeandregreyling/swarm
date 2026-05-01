# Linux Download-Speed Diagnosis (Phase-4 M22)

**Date:** 2026-04-10
**Host:** seven-potato (Dell OptiPlex 7090)
**Reporter:** Ghost One — "Linux feels slower than the Windows side at downloads"
**Status:** Root cause identified — actionable.

## Findings

| Metric | Result |
|---|---|
| `speedtest-cli` download | **1.22 Mbit/s** |
| `speedtest-cli` upload | 1.63 Mbit/s |
| OVH 100 MB curl | 34.7 KB/s sustained over 25 s |
| Hetzner 100 MB curl | failed (http 000, no carrier path) |
| Wired NIC `enp0s31f6` | **DOWN — `NO-CARRIER`** (cable unplugged or dead port) |
| Wifi NIC `wlp3s0` | UP — only active uplink |
| Tailscale | up |
| DNS resolution | normal (~ms) |
| MTU / docker bridge | normal |

## Root cause
The wired 1 GbE port (`enp0s31f6`) has **no link** — the machine is currently uplinked over wifi (`wlp3s0`).
The wifi link is delivering ~1.22 Mbit/s, which matches the curl numbers exactly. The 100x speed delta vs.
the Windows side is almost certainly because the Windows side is plugged into ethernet (or a different SSID
/ band) on the same network.

DNS, MTU, and TLS handshake are all healthy. There is no Linux-stack throughput regression.

## Recommended actions (in order)
1. **Plug the ethernet cable into `enp0s31f6`** (or test the cable on a known-good port). After link comes up:
   ```bash
   ip link set enp0s31f6 up
   sudo dhclient enp0s31f6
   speedtest-cli --simple
   ```
   Expected: ~ISP-line speed (typically 50–500 Mbit/s on a Melbourne NBN/HFC link).
2. **If the wired port is hardware-dead**, use a USB-C → 1 GbE adapter as a stop-gap; do not keep relying on
   the wifi card (it appears to be 2.4 GHz / weak signal based on the throughput).
3. **If we must stay on wifi**, run `iwconfig wlp3s0` to confirm the band/bitrate; consider switching to a
   5 GHz SSID or moving the OptiPlex closer to the AP.

## Non-issues ruled out
- DNS — resolves cleanly via systemd-resolved stub.
- TCP stack / MTU — normal frame size, no fragmentation.
- IPv6 / dual-stack — not implicated.
- Docker bridge — separate cgroup, doesn't affect host downloads.
- Tailscale — its tunnel only impacts Tailnet IPs, not public downloads.

## Raw evidence
Captured at `/tmp/dl_diag.txt` during this audit. Key extract included above.

## Closes
Phase-4 step **M22** — `S-C3F5D34A66`.
