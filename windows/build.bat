@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: Fridays Windows Build
:: Output: dist\Fridays\Fridays.exe  (portable folder — copy anywhere)
:: ─────────────────────────────────────────────────────────────────────────────
setlocal

set SCRIPT=%~dp0
set ROOT=%SCRIPT%..

echo [Build] Installing dependencies...
pip install pywebview pystray pillow pyinstaller --quiet

echo [Build] Cleaning previous build...
if exist "%SCRIPT%build" rmdir /s /q "%SCRIPT%build"
if exist "%SCRIPT%dist"  rmdir /s /q "%SCRIPT%dist"

echo [Build] Bundling Fridays...

pyinstaller ^
  --noconfirm ^
  --onedir ^
  --windowed ^
  --name Fridays ^
  --distpath "%SCRIPT%dist" ^
  --workpath "%SCRIPT%build" ^
  --specpath "%SCRIPT%" ^
  --add-data "%ROOT%\frontend\templates;frontend\templates" ^
  --add-data "%ROOT%\frontend\static;frontend\static" ^
  --add-data "%ROOT%\frontend\blueprints;frontend\blueprints" ^
  --add-data "%ROOT%\frontend\services.py;frontend" ^
  --add-data "%ROOT%\frontend\terminal.py;frontend" ^
  --add-data "%ROOT%\frontend\theme_engine.py;frontend" ^
  --add-data "%ROOT%\utils;utils" ^
  --add-data "%ROOT%\agents;agents" ^
  --add-data "%ROOT%\fridays;fridays" ^
  --add-data "%ROOT%\lib;lib" ^
  --add-data "%ROOT%\core;core" ^
  --paths "%ROOT%" ^
  --paths "%ROOT%\frontend" ^
  --paths "%ROOT%\utils" ^
  --hidden-import flask ^
  --hidden-import flask.templating ^
  --hidden-import jinja2 ^
  --hidden-import ollama ^
  --hidden-import webview ^
  --hidden-import pystray ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --hidden-import sqlite3 ^
  --hidden-import anthropic ^
  --hidden-import openai ^
  --hidden-import psutil ^
  --hidden-import requests ^
  --hidden-import tkinter ^
  "%SCRIPT%launcher.py"

echo.
if exist "%SCRIPT%dist\Fridays\Fridays.exe" (
  echo [Build] SUCCESS
  echo.
  echo Portable app: dist\Fridays\
  echo Copy that folder anywhere and run Fridays.exe
  echo.
  echo On first launch Fridays will create:
  echo   dist\Fridays\swarm_memory.db   ^(database^)
  echo   dist\Fridays\sandpits\         ^(agent workspaces^)
) else (
  echo [Build] FAILED — check output above
)
pause
