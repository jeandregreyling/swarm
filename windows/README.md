# Fridays on Windows

This folder contains the Windows installer + launcher. The Linux side runs from `/home/seven/swarm` on `nvme1n1` (ext4); the Windows side runs from a clone of this repo on the **LLM** NTFS partition (`nvme0n1p6`, mounted as `L:\` in Windows).

GitHub is the source of truth. Both sides `git pull` to stay in sync.

## Prerequisites (one-time, done by you outside this script)

1. **Python 3.11+** — https://www.python.org/downloads/ (tick *Add python.exe to PATH*)
2. **Ollama for Windows** — https://ollama.com/download/windows
3. **Git for Windows** — https://git-scm.com/download/win

## First install

Open Command Prompt or PowerShell on Windows, then:

```bat
L:
cd L:\swarm
windows\install-fridays.bat
```

This will:

- Create a project-local Python venv in `L:\swarm\.venv-win\`
- Install Python dependencies from `windows\requirements-windows.txt`
- Pull the four hot-path Ollama models (qwen2.5, gemma3, qwen, llama3.2)

## Daily launch

```bat
L:\swarm\windows\start-fridays.bat
```

This starts Ollama (if not running), boots the Flask app on `http://localhost:5050`, and opens it in your default browser. Closing the browser does **not** stop Fridays — close the console window or use the system tray.

## Updating from Linux

When you've made changes on the Linux side and pushed to GitHub:

```bat
L:
cd L:\swarm
git pull
```

If `requirements-windows.txt` changed, re-run `install-fridays.bat`.

## Updating from Windows

When you've made changes on the Windows side:

```bat
git add -A
git commit -m "windows: <what you changed>"
git push
```

Then on Linux:

```bash
cd /home/seven/swarm
git pull
```

## Layout

```
windows/
  install-fridays.bat       one-time setup (venv + pip + ollama pull)
  start-fridays.bat         daily launcher
  launcher.py               Python entry point (browser/tray/splash)
  build.bat                 PyInstaller build (optional — produces .exe)
  requirements-windows.txt  pip dependencies for Windows
  README.md                 this file
```

## Troubleshooting

- **"Python is not on PATH"** → re-install Python and tick *Add python.exe to PATH*, or open `Edit environment variables for your account` and append the Python install dir + its `Scripts\` subdir.
- **Ollama port in use** → close the Ollama tray icon, then re-run `start-fridays.bat`.
- **"Module not found"** in console → re-run `install-fridays.bat`; pip dependencies likely changed after a `git pull`.
- **Slow file ops** → don't keep the project on `\\wsl$\...` from Windows. The NTFS partition is the right home for Windows-side editing.
