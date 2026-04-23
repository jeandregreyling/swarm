# Desktop Packaging — Seven's Swarm

## Overview

The `desktop/` directory contains the Tauri-2 configuration that wraps Seven's
Swarm as a native desktop application on the Dell OptiPlex 7090 ("Seven").
The wrapper is a thin chrome — it simply opens a window pointed at the local
Flask UI on `http://localhost:5050`.

## Phase-4 M23 — Rewire (2026-04-10)

The desktop scaffolding was previously incomplete (no `src/main.rs`, broken
config schema URL, `frontendDist` pointing at a static folder that doesn't
exist for a Flask-served app). Now fixed:

- `src-tauri/src/main.rs` — minimal Tauri 2 entrypoint.
- `src-tauri/build.rs` — required by `tauri-build`.
- `src-tauri/Cargo.toml` — added `tauri-plugin-shell`, `[lib]`, `[[bin]]`.
- `tauri.conf.json` — schema → `schema.tauri.app/config/2`, single window
  with `url: http://localhost:5050`, frontendDist also points at the live URL,
  CSP widened to allow connections to the Flask backend, MSI target removed
  (we ship Linux only on Seven).

## Prerequisites

```bash
sudo apt install build-essential curl wget file libssl-dev \
  libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev libwebkit2gtk-4.1-dev
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install tauri-cli --version "^2"
```

## Development

```bash
# 1. Make sure the Flask backend is running (it normally is, via systemd)
systemctl --user --no-pager status swarm-terminal || \
  sudo systemctl status swarm-terminal

# 2. Launch the Tauri dev window (auto-reload)
cd /home/seven/swarm/desktop
cargo tauri dev
```

## Building a release bundle

```bash
cd /home/seven/swarm/desktop
cargo tauri build
```

Output:
- `desktop/src-tauri/target/release/bundle/deb/sevens-swarm_4.0.0_amd64.deb`
- `desktop/src-tauri/target/release/bundle/appimage/sevens-swarm_4.0.0_amd64.AppImage`

The AppImage is the easiest way to launch on Seven without installing the
.deb — drop it on the desktop, `chmod +x`, double-click.

## Headless / server-only mode

If you only need the Flask UI (no native window), just leave the systemd
unit running and open `http://localhost:5050` (or the Tailscale IP) in any
browser. The Tauri wrapper is purely cosmetic.

## File map

```
desktop/
├── tauri.conf.json          — App config (window + CSP + bundle targets)
├── README.md                — This file
└── src-tauri/
    ├── Cargo.toml           — Rust deps (tauri 2, tauri-plugin-shell)
    ├── build.rs             — tauri_build::build()
    └── src/
        └── main.rs          — Tauri entrypoint
```

## Known limitations

- Icons under `icons/` are not yet committed — `cargo tauri build` will
  prompt for missing icons; generate them with
  `cargo tauri icon path/to/seven.png` before the first build.
- Auto-launch on login is not configured here — handled by the systemd
  user target on Seven, not by Tauri.

