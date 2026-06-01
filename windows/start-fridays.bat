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
set "FRIDAYS_NO_PAUSE=%FRIDAYS_NO_PAUSE%"

call :resolve_ollama

set "ROOT=%~dp0.."
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Write-Output ((Get-Item '%~dp0..').FullName)"`) do set "ROOT=%%I"

set "IS_UNC=0"
if "%ROOT:~0,2%"=="\\" set "IS_UNC=1"

if "%IS_UNC%"=="1" (
    if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
    set "VENV=%LOCALAPPDATA%\Fridays\venv-win"
    echo [..] UNC workspace detected. Using local Windows venv: %VENV%
) else (
    set "VENV=%ROOT%\.venv-win"
)

set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
    echo [..] Python venv missing at %VENV%
    echo [..] Running one-time install automatically
    set "FRIDAYS_NO_PAUSE=1"
    set "FRIDAYS_SKIP_OLLAMA_PULL=1"
    set "FRIDAYS_VENV_PATH=%VENV%"
    call "%ROOT%\windows\install-fridays.bat"
    if errorlevel 1 (
        echo [ERROR] Windows install failed.
        if /i not "%FRIDAYS_NO_PAUSE%"=="1" pause
        exit /b 1
    )
    if not exist "%PY%" (
        echo [ERROR] Python venv still missing after install.
        if /i not "%FRIDAYS_NO_PAUSE%"=="1" pause
        exit /b 1
    )
)

"%PY%" -c "import flask, requests, psutil" >nul 2>nul
if errorlevel 1 (
    echo [..] Windows venv exists but core app deps are missing
    echo [..] Repairing venv via windows\install-fridays.bat
    set "FRIDAYS_NO_PAUSE=1"
    set "FRIDAYS_SKIP_OLLAMA_PULL=1"
    set "FRIDAYS_VENV_PATH=%VENV%"
    call "%ROOT%\windows\install-fridays.bat"
    if errorlevel 1 (
        echo [ERROR] Windows dependency repair failed.
        if /i not "%FRIDAYS_NO_PAUSE%"=="1" pause
        exit /b 1
    )
    "%PY%" -c "import flask, requests, psutil" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Windows venv still missing core app deps after repair.
        if /i not "%FRIDAYS_NO_PAUSE%"=="1" pause
        exit /b 1
    )
)

:: ── Make sure Ollama is up ─────────────────────────────────────────────────
:: Point Ollama at the shared model store on the NTFS data partition.
:: Both Windows and WSL read from this same directory so models are only stored once.
if not defined OLLAMA_MODELS (
    if exist "F:\.ollama\models" (
        set "OLLAMA_MODELS=F:\.ollama\models"
    )
)
if defined OLLAMA_CMD (
    powershell -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri http://localhost:11434/api/tags | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
    if errorlevel 1 (
        echo [..] Starting Ollama server in background (models: %OLLAMA_MODELS%)
        start "" /min "%OLLAMA_CMD%" serve
        timeout /t 3 /nobreak >nul
    ) else (
        echo [OK] Ollama already running.
    )
) else (
    echo [WARN] Ollama not found on this Windows machine. Local models will be unavailable.
)

:: ── Environment ────────────────────────────────────────────────────────────
set "SWARM_PLATFORM=windows"
set "SWARM_ENV=prod"
set "SWARM_ROOT=%ROOT%"
if not defined LOCALAPPDATA set "LOCALAPPDATA=%ROOT%"
set "FRIDAYS_DATA=%LOCALAPPDATA%\Fridays"
if not exist "%FRIDAYS_DATA%" mkdir "%FRIDAYS_DATA%" >nul 2>nul
set "SWARM_DB_PATH=%FRIDAYS_DATA%\swarm_memory.db"
set "SWARM_MEMORY_DB=%SWARM_DB_PATH%"
set "SWARM_HIVE_DB=%FRIDAYS_DATA%\swarm_hive.db"
set "PORT=5050"
set "PYTHONPATH=%ROOT%;%ROOT%\frontend;%ROOT%\utils"
set "UI_URL=http://127.0.0.1:%PORT%/ui"
set "FRIDAYS_RUNTIME_ID=source:%ROOT%"

:: ── Reuse existing healthy runtime instead of spawning duplicates ──────────
powershell -Command "$expected = [System.IO.Path]::GetFullPath('%ROOT%'); try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri http://127.0.0.1:%PORT%/_health; if ($r.StatusCode -ne 200) { exit 1 }; $j = $r.Content | ConvertFrom-Json; if ($j.runtime_id -eq ('source:' + $expected)) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
    echo [OK] Fridays already running on port %PORT%
    echo [..] Opening native Fridays app window (no browser fallback)
    "%PY%" "%ROOT%\windows\launcher.py"
    if errorlevel 1 (
        echo [WARN] Native launcher failed; opening browser as last resort.
        start "" "%UI_URL%"
        exit /b 0
    )
    exit /b 0
)

:: ── Pre-flight: launcher.py if present, else direct terminal.py ────────────
echo [..] Launching Fridays via windows\launcher.py
"%PY%" "%ROOT%\windows\launcher.py"
if errorlevel 1 (
    echo [WARN] Native launcher failed; starting Flask directly.
    pushd "%ROOT%\frontend"
    start "" http://localhost:5050/ui
    "%PY%" -c "from terminal import create_app; from wsgiref.simple_server import make_server; make_server('127.0.0.1', 5050, create_app()).serve_forever()"
    popd
)

endlocal
goto :eof

:resolve_ollama
set "OLLAMA_CMD="
where ollama >nul 2>nul
if not errorlevel 1 (
    set "OLLAMA_CMD=ollama"
    goto :eof
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    goto :eof
)
if exist "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe" (
    set "OLLAMA_CMD=%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe"
    goto :eof
)
if exist "%ProgramFiles%\Ollama\ollama.exe" (
    set "OLLAMA_CMD=%ProgramFiles%\Ollama\ollama.exe"
    goto :eof
)
if exist "%ProgramFiles(x86)%\Ollama\ollama.exe" (
    set "OLLAMA_CMD=%ProgramFiles(x86)%\Ollama\ollama.exe"
    goto :eof
)
goto :eof
