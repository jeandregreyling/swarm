@echo off
:: ─────────────────────────────────────────────────────────────────────────────
::  Fridays — One-time Windows install
::
::  Requires (manual, before running this script):
::    1. Python 3.11+ from https://www.python.org/downloads/  (tick "Add to PATH")
::    2. Ollama from https://ollama.com/download/windows
::    3. Git from https://git-scm.com/download/win  (only needed for updates)
::
::  This script:
::    • Creates a project-local venv in `.venv-win\`
::    • Installs Python dependencies
::    • Tells Ollama to pull the four hot-path models
:: ─────────────────────────────────────────────────────────────────────────────

setlocal EnableDelayedExpansion
set "FRIDAYS_NO_PAUSE=%FRIDAYS_NO_PAUSE%"
set "FRIDAYS_SKIP_OLLAMA_PULL=%FRIDAYS_SKIP_OLLAMA_PULL%"
set "FRIDAYS_VENV_PATH=%FRIDAYS_VENV_PATH%"

:: Resolve the project root (parent of this script's folder)
set "ROOT=%~dp0.."
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Write-Output ((Get-Item '%~dp0..').FullName)"`) do set "ROOT=%%I"

echo.
echo ============================================================
echo   Fridays — Windows install
echo   Project root: %ROOT%
echo ============================================================
echo.

:: ── Step 1 — Python ────────────────────────────────────────────────────────
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not on PATH.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH" during install.
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version') do set "PYVER=%%v"
echo [OK] Python detected: %PYVER%

:: ── Step 2 — venv ──────────────────────────────────────────────────────────
if defined FRIDAYS_VENV_PATH (
    set "VENV=%FRIDAYS_VENV_PATH%"
) else (
    set "VENV=%ROOT%\.venv-win"
)
if exist "%VENV%\Scripts\python.exe" (
    echo [OK] Existing venv found at %VENV%
) else (
    echo [..] Creating venv at %VENV%
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause & exit /b 1
    )
)

:: ── Step 3 — pip install ───────────────────────────────────────────────────
echo [..] Upgrading pip
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip --quiet

set "REQ=%ROOT%\windows\requirements-windows.txt"
if exist "%REQ%" (
    echo [..] Installing windows\requirements-windows.txt
    "%VENV%\Scripts\python.exe" -m pip install -r "%REQ%"
) else (
    echo [WARN] windows\requirements-windows.txt missing — installing minimal set
    "%VENV%\Scripts\python.exe" -m pip install flask requests pillow ollama anthropic openai psutil pywebview pystray
)

:: ── Step 4 — Ollama ────────────────────────────────────────────────────────
where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo [WARN] Ollama not found on PATH.
    echo        Install Ollama from https://ollama.com/download/windows
    echo        then re-run this installer.
    goto :done
)
echo [OK] Ollama detected.

if /i "%FRIDAYS_SKIP_OLLAMA_PULL%"=="1" (
    echo [..] Skipping Ollama model pulls because FRIDAYS_SKIP_OLLAMA_PULL=1
    goto :done
)

echo.
echo ============================================================
echo   Pulling hot-path models (this can take a while)
echo ============================================================
for %%M in (qwen2.5:latest gemma3:latest qwen:latest llama3.2:latest) do (
    echo [..] ollama pull %%M
    ollama pull %%M
)

:done
echo.
echo ============================================================
echo   Install complete.
echo   Launch Fridays with:  windows\start-fridays.bat
echo ============================================================
echo.
if /i not "%FRIDAYS_NO_PAUSE%"=="1" pause
endlocal
