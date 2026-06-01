"""Log Slice C (PyInstaller MSI installer) completion."""
from __future__ import annotations
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.knowledge import projects  # type: ignore

PROJECT_ID = "P-94531FE267"

CONTENT = """[MILESTONE] Slice C — PyInstaller -> WiX v4 MSI installer wired — 2026-06-01

User picked PyInstaller MSI as the Windows packaging path. The portable
PyInstaller pipeline (windows/build.bat -> windows/dist/Fridays/) already
existed; Slice C adds the MSI wrapper on top.

== ADDED ==

windows/installer/Fridays.wxs
  WiX v4 authoring. Per-user install scope (Scope="perUser") so no admin
  prompt. Install root: %LOCALAPPDATA%\\Programs\\Fridays\\.
  Features:
    - Component group ref `HarvestedFiles` (generated at build time).
    - Start Menu shortcut (Fridays\\Fridays.lnk).
    - Desktop shortcut.
    - HKCU registry entries for InstallPath + Add/Remove Programs icon.
    - MajorUpgrade with descending error guard.
    - WixUI_InstallDir wizard + "Launch Fridays now" exit option.
  Stable GUIDs for UpgradeCode and each component so upgrades are clean.
  User data stays in %LOCALAPPDATA%\\Fridays (launcher.py already
  handles this), so uninstall/upgrade never touches the SQLite DB.

windows/build_msi.bat
  Orchestrates the two-step build:
    1. `wix harvest dir windows\\dist\\Fridays -cg HarvestedFiles
        -dr INSTALLFOLDER -srd -ag -o windows\\installer\\Files.wxs`
    2. `wix build -arch x64 -ext WixToolset.UI.wixext
        -ext WixToolset.Util.wixext -d SourceDir=... -bindpath ...
        -o windows\\installer\\Fridays.msi Fridays.wxs Files.wxs`
  Pre-flight checks: `where wix`, presence of Fridays.exe in dist.

windows/README.md
  New "Build MSI Installer" section documenting:
    - Prereqs: .NET 8 SDK, `dotnet tool install --global wix`, two
      extensions (UI.wixext + Util.wixext).
    - Build sequence: build.bat -> build_msi.bat.
    - Silent test install / uninstall via msiexec /qb and /qn.

tests/test_windows_launcher_packaging.py
  New test `test_windows_msi_installer_files_exist` asserts:
    - Fridays.wxs + build_msi.bat both exist.
    - ComponentGroup id `HarvestedFiles` matches between harvest cmd
      and .wxs reference.
    - Scope is perUser (no admin).
    - DirectoryRef `INSTALLFOLDER` matches between harvest target and
      Fridays.wxs shortcut + registry components.

== TEST EVIDENCE ==
pytest tests/test_windows_launcher_packaging.py -> 4 passed.
(2 original + 1 pre-existing services-package check + 1 new MSI guard.)

== CANNOT TEST FROM WSL ==
The MSI itself cannot be built from Linux: `wix` is a .NET 8 tool that
runs on Windows. The author has been instructed (README) to run
build.bat + build_msi.bat from a Windows shell. The .wxs and the
orchestrator are validated only structurally here.

== STATE LINKAGE ==
Slice C closes the open packaging question raised under steps
S-F7C134D9C6 / S-1B90B67986 / S-BAAE9C22D8. After build_msi.bat
produces Fridays.msi the operator can distribute it directly; no further
CI plumbing is in scope for this slice.

== REMAINING (post-Slice-C) ==
- Wire up Ollama in WSL (Library 'nomic-embed-text' is still blocked
  because `ollama` isn't installed in the runtime).
- Optional: GitHub Actions runner that calls build.bat + build_msi.bat
  on a `windows-latest` image and uploads the MSI as a release asset.
- Optional: signed MSI (signtool + EV cert) when a code-signing cert
  is available.
"""

try:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, author="copilot-audit", kind="milestone")
except TypeError:
    note = projects.add_blackboard_note(PROJECT_ID, CONTENT, kind="milestone")
print(f"project_id={PROJECT_ID}")
print(f"created_note_id={note.get('id') if isinstance(note, dict) else note}")
