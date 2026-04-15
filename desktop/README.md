# Desktop Packaging — Seven's Swarm

## Overview

The desktop/ directory contains Tauri configuration for packaging Seven's Swarm
as a native desktop application. The Tauri wrapper connects to the Flask backend
running on localhost:5050.

## Prerequisites

- Rust toolchain (rustup.rs)
- Node.js 18+
- Tauri CLI: `cargo install tauri-cli`
- System dependencies: `sudo apt install libwebkit2gtk-4.1-dev build-essential`

## Development

```bash
# Start the Flask backend
cd /path/to/swarm && python3 frontend/terminal.py

# In another terminal, start Tauri dev mode
cd desktop && cargo tauri dev
```

## Building

```bash
cd desktop && cargo tauri build
```

Output will be in `desktop/src-tauri/target/release/bundle/`.

## Headless Mode

For server-only deployment without the desktop wrapper:

```bash
python3 scripts/desktop_launcher.py --headless
```

## Architecture

```
desktop/
├── tauri.conf.json      — Tauri app configuration
├── src-tauri/
│   └── Cargo.toml       — Rust dependencies
└── README.md            — This file
```

The Tauri window loads `http://localhost:5050` served by Flask. All logic
stays in Python; the desktop wrapper provides a native window with system
tray integration and OS-level notifications.
