@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: Fridays MSI Build (WiX v4)
:: Inputs : windows\dist\Fridays\         (output of build.bat)
:: Output : windows\installer\Fridays.msi
::
:: Prerequisites (one-time):
::   1. Install .NET 8 SDK   : https://dotnet.microsoft.com/download
::   2. Install WiX v4 tool  : dotnet tool install --global wix
::   3. Add UI extension     : wix extension add -g WixToolset.UI.wixext
::   4. Add Util extension   : wix extension add -g WixToolset.Util.wixext
:: ─────────────────────────────────────────────────────────────────────────────
setlocal EnableDelayedExpansion

set SCRIPT=%~dp0
set INSTALLER=%SCRIPT%installer
set DIST=%SCRIPT%dist\Fridays
set WXS=%INSTALLER%\Fridays.wxs
set HARVEST=%INSTALLER%\Files.wxs
set OUT=%INSTALLER%\Fridays.msi

:: ─── Sanity ────────────────────────────────────────────────────────────────
where wix >nul 2>&1
if errorlevel 1 (
  echo [MSI] wix command not found. Install: dotnet tool install --global wix
  exit /b 1
)

if not exist "%DIST%\Fridays.exe" (
  echo [MSI] %DIST%\Fridays.exe missing. Run windows\build.bat first.
  exit /b 1
)

:: ─── Harvest the portable dist folder into a component group ───────────────
echo [MSI] Harvesting %DIST% ...
wix harvest dir "%DIST%" ^
  -cg HarvestedFiles ^
  -dr INSTALLFOLDER ^
  -srd ^
  -ag ^
  -o "%HARVEST%"
if errorlevel 1 (
  echo [MSI] harvest failed.
  exit /b 1
)

:: ─── Build the MSI ─────────────────────────────────────────────────────────
echo [MSI] Building MSI ...
wix build ^
  -arch x64 ^
  -ext WixToolset.UI.wixext ^
  -ext WixToolset.Util.wixext ^
  -d SourceDir="%DIST%" ^
  -bindpath "%DIST%" ^
  -o "%OUT%" ^
  "%WXS%" "%HARVEST%"

if errorlevel 1 (
  echo [MSI] build failed.
  exit /b 1
)

echo.
echo [MSI] SUCCESS
echo Installer: %OUT%
echo.
echo Test install (per-user, no admin):
echo   msiexec /i "%OUT%" /qb
echo Silent uninstall:
echo   msiexec /x "%OUT%" /qn
endlocal
