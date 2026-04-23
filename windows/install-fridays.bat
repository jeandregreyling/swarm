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

:: Resolve the project root (parent of this script's folder)
pushd "%~dp0.."
set "ROOT=%CD%"
popd

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
set "VENV=%ROOT%\.venv-win"
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
pause
endlocal
