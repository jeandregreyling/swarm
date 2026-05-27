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

The launcher starts the Flask app on `http://127.0.0.1:5050/ui`. If
`pywebview` is available it opens a desktop window; otherwise it opens the
default browser.

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
