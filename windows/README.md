# Fridays Windows App

This folder contains the Windows launcher and build scripts for running
Fridays as a local desktop app.

## Run From Source

Prerequisites:

- Python 3.11 or newer from https://www.python.org/downloads/
- Git for updates: https://git-scm.com/download/win
- Ollama for local models: https://ollama.com/download/windows

From the repo root in Command Prompt:

```bat
windows\install-fridays.bat
windows\start-fridays.bat
```

From WSL in the repo root:

```bash
./windows/run-fridays-from-wsl.sh start
```

The WSL wrapper auto-runs the Windows installer on first launch if
`.venv-win\Scripts\python.exe` is missing.

When launching from a UNC/WSL path (for example `\\wsl$\...`), the launcher
automatically uses a local Windows venv at `%LOCALAPPDATA%\Fridays\venv-win`
so native window dependencies (pywebview/.NET loader) work correctly.

The launcher starts the Flask app on `http://127.0.0.1:5050/ui` and opens a
native desktop window (pywebview). Browser fallback is disabled by default so
the app behaves like a real Windows app.

If you explicitly want browser fallback for troubleshooting, set:

```bat
set FRIDAYS_ALLOW_BROWSER_FALLBACK=1
windows\start-fridays.bat
```

## Build Portable App

Run this from the repo root on Windows:

```bat
windows\build.bat
```

The output is:

```text
windows\dist\Fridays\Fridays.exe
```

Copy the whole `windows\dist\Fridays\` folder to keep the executable and its
runtime files together.

## Build MSI Installer

Wraps the portable `windows\dist\Fridays\` folder in a per-user MSI
(`%LOCALAPPDATA%\Programs\Fridays`, no admin prompt). Authoring lives in
[installer/Fridays.wxs](installer/Fridays.wxs) — WiX v4 syntax.

One-time prerequisites on Windows:

```bat
:: 1. .NET 8 SDK from https://dotnet.microsoft.com/download
:: 2. WiX v4 + extensions:
dotnet tool install --global wix
wix extension add -g WixToolset.UI.wixext
wix extension add -g WixToolset.Util.wixext
```

Then, from the repo root on Windows:

```bat
windows\build.bat        :: produces windows\dist\Fridays\
windows\build_msi.bat    :: produces windows\installer\Fridays.msi
```

Test install (silent, per-user):

```bat
msiexec /i windows\installer\Fridays.msi /qb
msiexec /x windows\installer\Fridays.msi /qn
```

The MSI registers Add/Remove Programs entries under HKCU, drops a Start Menu
and Desktop shortcut, and keeps user data under `%LOCALAPPDATA%\Fridays` so
uninstall/upgrade never touches the DB.

## Data Location

The source launcher stores data under the repo root:

- `swarm_memory.db`
- `sandpits\`
- `logs\`

The portable app stores data next to `Fridays.exe`, so user data survives app
updates when the executable folder is replaced carefully.

## Regression Guards

The Windows build is covered by:

```bat
python -m pytest -q tests\test_windows_launcher_packaging.py
```

That test verifies the PyInstaller data inputs exist and that the current
`frontend\services\` package is bundled instead of the old removed
`frontend\services.py` file.
