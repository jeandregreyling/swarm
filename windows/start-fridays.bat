@echo off
:: ─────────────────────────────────────────────────────────────────────────────
::  Fridays — Windows launcher
::
::  Starts Ollama (if not already running), then launches the Flask UI on
::  http://localhost:5050 and opens it in your default browser.
::
::  First time? Run windows\install-fridays.bat first.
:: ─────────────────────────────────────────────────────────────────────────────

setlocal EnableDelayedExpansion

pushd "%~dp0.."
set "ROOT=%CD%"
popd

set "VENV=%ROOT%\.venv-win"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
    echo [ERROR] Python venv missing at %VENV%
    echo         Run  windows\install-fridays.bat  first.
    pause & exit /b 1
)

:: ── Make sure Ollama is up ─────────────────────────────────────────────────
where ollama >nul 2>nul
if not errorlevel 1 (
    powershell -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri http://localhost:11434/api/tags | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
    if errorlevel 1 (
        echo [..] Starting Ollama server in background
        start "" /min "ollama" serve
        timeout /t 3 /nobreak >nul
    ) else (
        echo [OK] Ollama already running.
    )
) else (
    echo [WARN] Ollama not on PATH. Local models will be unavailable.
)

:: ── Environment ────────────────────────────────────────────────────────────
set "SWARM_PLATFORM=windows"
set "SWARM_ENV=prod"
set "SWARM_ROOT=%ROOT%"
set "SWARM_DB_PATH=%ROOT%\swarm_memory.db"
set "PORT=5050"
set "PYTHONPATH=%ROOT%;%ROOT%\frontend;%ROOT%\utils"

:: ── Pre-flight: launcher.py if present, else direct terminal.py ────────────
set "LAUNCHER=%ROOT%\windows\launcher.py"
if exist "%LAUNCHER%" (
    echo [..] Launching Fridays via windows\launcher.py
    "%PY%" "%LAUNCHER%"
) else (
    echo [..] Launching Fridays Flask app directly
    pushd "%ROOT%\frontend"
    start "" http://localhost:5050/ui
    "%PY%" -c "from terminal import create_app; from wsgiref.simple_server import make_server; make_server('127.0.0.1', 5050, create_app()).serve_forever()"
    popd
)

endlocal
