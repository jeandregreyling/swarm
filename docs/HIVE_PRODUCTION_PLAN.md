# Swarm Hive — production readiness plan

> Written 2026-05-03 in response to: "I'm not shipping this build, it still
> needs refinement … click-through setup … VPN isn't even in house yet."

This document is the roadmap from the current alpha (curl-bash bootstrap,
Tailscale-on-the-side) to a shippable product. It is intentionally
opinionated and dated so future me can hold past me to it.

## 1. Definition of "shippable"

A non-technical user, on any of the four target platforms (Linux / macOS /
Windows / Android), should be able to:

1. Receive an invite link from the Hive leader.
2. Open the link → download a single artefact.
3. Double-click / tap → click Next → click Install → done.
4. The device shows up in the leader's Monitor view within 30 seconds.
5. All traffic between leader and node travels over an in-house mesh
   overlay — no third-party VPN dependency.

Anything that requires opening a terminal, copying a curl command, or
reading a README is **not shippable** by this definition.

## 2. Current state (what we have)

- `ops/hive_agent.py` — std-lib agent, runs on Linux/macOS/Windows.
- `ops/install/install_{linux,macos}.sh`, `install_windows.ps1` — system-
  service installers. Require terminal access.
- `ops/install/bootstrap.{sh,ps1}` — one-liner shims served by the leader.
- `frontend/blueprints/hive.py` — `/api/hive/install/` manifest + per-file
  routes; allow-listed, traversal-safe.
- Monitor view "Add a device" panel with copy-paste commands.
- Tests: 55 hive tests + 11 install-route tests, all green.
- Bullshit gate: GREEN 97/100.

## 3. Gaps (what blocks shipping)

| # | Gap                                                            | Severity |
|---|----------------------------------------------------------------|----------|
| 1 | No click-through installer for any platform                    | Critical |
| 2 | Network overlay is Tailscale (third-party, not in-house)       | Critical |
| 3 | No mDNS / leader auto-discovery on the LAN                     | High     |
| 4 | Tokens are minted server-side then emailed/copied — no QR/link | High     |
| 5 | No installer code signing → SmartScreen / Gatekeeper warnings  | High     |
| 6 | No Android client at all                                       | High     |
| 7 | No uninstaller UX (only manual `--uninstall` flag)             | Medium   |
| 8 | Self-update path: agent has no built-in upgrade channel        | Medium   |
| 9 | Logs ship to stderr only; no log shipping back to leader       | Medium   |
| 10| TLS off by default; HTTP-only on a LAN is a smell              | Medium   |

## 4. Roadmap

### Phase A — Click-through installers (this iteration)

**Goal:** Linux / macOS / Windows users double-click a single file and
arrive in the Hive without ever opening a terminal.

- A.1 `ops/install/hive_installer_core.py` — pure-Python, std-lib-only
  module containing all non-UI logic: leader probe, agent download,
  config write, service install dispatch. Headless-testable.
- A.2 `ops/install/hive_installer_gui.py` — Tkinter wizard (stdlib).
  Pages: **Welcome → Leader → Confirm → Install → Done**. Threads the
  network/install work so the UI stays responsive. Pure Python so a
  user with Python ≥3.10 can run it directly; we will package later.
- A.3 Serve `hive_installer_gui.py` from
  `/api/hive/install/hive_installer_gui.py` and surface a
  **Download installer** button in the Monitor Add Device panel.
- A.4 Tests for the core module (network mocked) + a route test that
  proves the installer ships with a valid `__main__` block.
- A.5 Documented manual smoke: `python3 hive_installer_gui.py` on this
  Linux dev box, click through, confirm node appears.

**Out of scope this phase:** native installer packaging (.msi / .pkg /
.AppImage / .deb), code signing, Android.

### Phase B — Native installer packaging

**Goal:** turn `hive_installer_gui.py` into platform-native artefacts.

- B.1 **Windows .exe**: PyInstaller --onefile from a clean Windows runner;
  embed icon; Authenticode sign with our cert; ship as
  `Swarm-Hive-Setup.exe`. Hosts at `/api/hive/install/setup.exe`.
- B.2 **macOS .pkg** + .app bundle: `pyinstaller --windowed`, wrap in
  `pkgbuild` + `productbuild`, Developer-ID sign, notarise.
- B.3 **Linux AppImage**: linuxdeploy + python3 plugin → single
  executable `Swarm-Hive.AppImage` users `chmod +x` and double-click.
  Optional: .deb via fpm for apt users.
- B.4 Each native artefact appears in `/api/hive/install/` manifest
  with a SHA-256 we publish. UI auto-detects the user-agent and
  recommends the correct download.

**Blocker:** we need a code-signing cert (DigiCert / Sectigo) for
Windows + a Developer-ID account for macOS notarisation. Until those
are bought, B.1/B.2 ship unsigned and the UI warns the user.

### Phase C — In-house mesh overlay (replace Tailscale)

**Goal:** delete the Tailscale dependency. Run our own WireGuard mesh
with a Hive-native control plane.

Architecture:

- **Data plane:** WireGuard. It is the right tool — kernel module on
  Linux/Android, userspace on macOS/Windows via wireguard-go. We are
  not writing our own crypto.
- **Control plane (new):** `core/hive/overlay/` — the leader is the
  WireGuard coordinator.
  - C.1 `core/hive/overlay/keys.py` — generate node keypairs (Curve25519
        via `cryptography` lib, which is the only new third-party dep
        we permit; std-lib `nacl` is not stdlib but is small).
  - C.2 `core/hive/overlay/coordinator.py` — leader-side: assign
        `100.96.x.y/32` addresses from a private pool, distribute peer
        lists, rotate preshared keys daily.
  - C.3 `core/hive/overlay/agent.py` — node-side: receive WG config,
        write `/etc/wireguard/swarm0.conf` (or platform equivalent),
        bring interface up via `wg-quick` / Windows service.
  - C.4 New routes:
        - `POST /api/hive/overlay/join` (token-authed) → returns
          assigned IP, peer list, server pubkey.
        - `GET  /api/hive/overlay/peers` (mTLS) → keep-alive peer
          delta sync.
        - `POST /api/hive/overlay/rotate` → leader broadcasts new
          PSK; nodes confirm; old PSK retires after T+60s.
- **NAT traversal:** STUN-derived public-IP echo (no TURN initially —
  if a peer is symmetric-NAT-bound the leader becomes its relay).
- **Boot order:** the GUI installer asks "Join the secure mesh now?"
  (default Yes). On Yes, it provisions WireGuard *before* enrolling
  the agent; the agent then talks to the leader exclusively over the
  overlay IP.
- **Tailscale removal:** once C.1–C.4 are green and at least three
  nodes have lived on the mesh for a week, rip out the Tailscale
  references in docs and ship a release note that flips the default.

**Why WireGuard and not pure-Python?** Because writing transport-layer
crypto from scratch is the lazy move dressed up as ambitious. We pick
the smallest in-house surface that is *actually in our control* —
control plane + topology + key rotation — and we let WireGuard do the
packet encryption. Our control plane is what makes it "in-house".

### Phase D — Discovery + frictionless enrolment

**Goal:** delete the "paste leader URL" step.

- D.1 mDNS advertisement on the leader (`_swarm-hive._tcp.local.`)
  using std-lib `socket` + a tiny zeroconf shim (or vendored mdns).
- D.2 Installer auto-discovers leaders on the LAN, presents a list,
  user clicks one. Manual-URL stays as a fallback.
- D.3 Token delivery via signed deep link: the leader UI generates
  `swarm-hive://enrol?leader=…&token=…&exp=…`. Operator scans it
  with the device's camera (Android) or clicks it on the desktop.

### Phase E — Android

**Goal:** real APK, real Play-Store-ready experience.

- E.1 Kivy or BeeWare? Decision blocked on whether we can reuse the
  Python agent verbatim. Likely Kivy + python-for-android.
- E.2 Foreground service (Android requires this) for telemetry.
- E.3 WireGuard provisioning via the official WireGuard-Android
  library (their VpnService class).
- E.4 QR-code enrolment as the primary path.

Phase E does not start until Phases A–D are green on desktop.

### Phase F — Operations hardening

- F.1 TLS-by-default: Caddy or stdlib `http.server` with mkcert for LAN.
- F.2 Self-update channel: agent reads `GET /api/hive/agent/version`,
  compares against its embedded version, downloads + restarts if newer,
  with rollback on three consecutive failed health checks.
- F.3 Log shipping: agent batches stderr/journal into
  `POST /api/hive/logs` with backpressure.
- F.4 Uninstall path: `--uninstall` flag in installer; GUI surfaces
  "Remove this device" button in Monitor.
- F.5 SBOM + supply-chain: pin every dep, vendor what we can, audit on
  every release.

## 5. Order of execution

```
A  →  C  →  D  →  B  →  F  →  E
```

Click-through first because it is the loudest UX gap. The mesh
overlay (C) precedes packaging (B) because we don't want to ship
signed installers that hard-code a Tailscale assumption — we'd just
have to re-sign them. Discovery (D) is cheap once C exists. Then
packaging (B), then ops hardening (F), then Android (E).

## 6. Done-ness checklist (must all be true to call it shipped)

- [ ] A non-technical tester installed Hive on Linux, macOS, and Windows
      without ever typing a shell command.
- [ ] Tailscale is no longer mentioned in any runtime code or doc.
- [ ] Three Hive devices have run on the in-house overlay for ≥7 days
      with zero packet-loss alerts.
- [ ] The installer shows the leader's identity (TLS cert fingerprint
      or pubkey) before asking the user to enrol — defends against
      LAN-spoof attacks.
- [ ] Bullshit gate stays GREEN ≥95/100 for every commit on `main`.

## 7. What we are deliberately **not** doing

- No custom transport-layer crypto. WireGuard for packets, full stop.
- No "AI-driven autoconfig" magic. The control plane is a boring
  registry with key rotation.
- No paid SaaS dependency added. The whole point of Phase C is to
  *remove* one.
- No Electron. Tkinter for the wizard, native packagers for the
  release artefacts. Smaller binaries, smaller blast radius.
