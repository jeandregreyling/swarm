# Seven Desktop — macOS Install Guide

## Requirements
- macOS 10.13 or later
- [Rust](https://rustup.rs/) (install via `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- Xcode Command Line Tools (`xcode-select --install`)

## Quick Install (5 minutes)

```bash
# 1. Clone the repo (or scp the desktop/ folder from the server)
git clone git@github.com:jeandregreyling/swarm.git
cd swarm/desktop/src-tauri

# 2. Install Tauri CLI
cargo install tauri-cli --version '^2'

# 3. Build the DMG
cargo tauri build

# 4. Open the DMG and drag Seven.app to Applications
open target/release/bundle/dmg/Seven_1.0.0_*.dmg
```

## First Launch

Since the app is unsigned, macOS Gatekeeper will block it on first open.

**Do NOT double-click the app.** Instead:

1. Open **System Settings → Privacy & Security**
2. Scroll down to the "Security" section
3. Find "Seven" was blocked from opening
4. Click **Open Anyway**
5. Or right-click the app → **Open** → click **Open** in the dialog

## Configuration

1. Open Seven
2. Click **Settings** in the sidebar
3. Enter your leader URL (e.g. `http://100.87.66.45:5050`)
4. Save
5. Start chatting or enrol your Mac via **Join Swarm**

## What's Inside

One app. Not two. Seven handles:
- **Chat** — Talk to Seven and the swarm
- **Nodes** — See all connected Hive nodes (potato-2, etc.)
- **Join Swarm** — Enrol this Mac as a new node
- **Settings** — Leader URL, preferences

## Troubleshooting

**"cargo not found"** — Run `source $HOME/.cargo/env` or restart Terminal.

**"Seven.app is damaged"** — This is Gatekeeper. Run:
```bash
xattr -rd com.apple.quarantine /Applications/Seven.app
```

**Can't connect to leader** — Make sure the leader URL is reachable from your Mac (same Tailscale network or public IP).
