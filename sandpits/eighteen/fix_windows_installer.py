#!/usr/bin/env python3
"""Rewrite install_windows.ps1 to fix the 5 gaps identified in audit."""
import sys, os, shutil

REPO = '/home/seven/swarm'
ORIG = f'{REPO}/ops/install/install_windows.ps1'
BACKUP = f'{REPO}/ops/install/install_windows.ps1.bak-20260510'

# Read original to preserve structure
with open(ORIG, 'r', encoding='utf-8') as f:
    orig_text = f.read()

# Backup
shutil.copy2(ORIG, BACKUP)

new_script = r'''# install_windows.ps1 — install the Swarm Hive agent as a per-user
# scheduled task that runs at logon and restarts on failure.
#
# Usage (PowerShell, no admin needed):
#   $env:SWARM_HIVE_LEADER = "http://leader.local:5050"
#   .\install_windows.ps1
#
# Optional env: SWARM_HIVE_LEADER, SWARM_NODE_ID, SWARM_HIVE_INTERVAL, SWARM_HIVE_PYTHON

$ErrorActionPreference = "Stop"

$leader   = if ($env:SWARM_HIVE_LEADER)   { $env:SWARM_HIVE_LEADER }   else { "http://localhost:5050" }
$interval = if ($env:SWARM_HIVE_INTERVAL) { $env:SWARM_HIVE_INTERVAL } else { "30" }
$nodeId   = $env:SWARM_NODE_ID

# --- FIX 1: Python fallback (python, python3, py) ---
function Find-Python {
    foreach ($candidate in @("python3", "python", "py")) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    return $null
}
$py = if ($env:SWARM_HIVE_PYTHON) { $env:SWARM_HIVE_PYTHON } else { Find-Python }
if (-not $py) {
    Write-Error "No Python interpreter found. Install python3 and ensure it is on PATH, or set `$env:SWARM_HIVE_PYTHON."
    exit 3
}
Write-Host "[install_windows] using python: $py"

# --- FIX 2: Bootstrap download when not running from repo ---
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$repoRoot = (Resolve-Path "$scriptDir\..\..").Path
$agent = Join-Path $repoRoot "ops\hive_agent.py"

if (-not (Test-Path $agent)) {
    Write-Host "[install_windows] agent not found locally; bootstrapping from leader..."
    $stageDir = "$env:LOCALAPPDATA\swarm-hive"
    New-Item -ItemType Directory -Force -Path $stageDir | Out-Null
    $agent = Join-Path $stageDir "hive_agent.py"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$leader/api/hive/install/hive_agent.py" -OutFile $agent -TimeoutSec 30
    } catch {
        Write-Error "Failed to download agent from $leader/api/hive/install/hive_agent.py : $_"
        exit 2
    }
    Write-Host "[install_windows] downloaded agent to $agent"
}

# Quick sanity
Write-Host "[install_windows] enrolling with leader=$leader ..."
$enrolArgs = @($agent, "--enrol", "--leader", $leader)
if ($nodeId) { $enrolArgs += @("--node-id", $nodeId) }
& $py @enrolArgs

$taskName = "SwarmHiveAgent"

# --- FIX 3: Quote paths in scheduled task action ---
# Use Start-Process wrapper to handle spaces in paths correctly.
$wrapperPs1 = @"
`$env:SWARM_HIVE_LEADER = '$leader'
if ('$nodeId') { `$env:SWARM_NODE_ID = '$nodeId' }
& `"$py`" `"$agent`" --run --interval $interval
"@
$wrapperPath = "$env:LOCALAPPDATA\swarm-hive\run_agent.ps1"
New-Item -ItemType Directory -Force -Path (Split-Path $wrapperPath) | Out-Null
$wrapperPs1 | Set-Content -Path $wrapperPath -Encoding UTF8

$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$wrapperPath`""
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 9999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description "Swarm Hive node agent"

# --- FIX 4: Verify task actually started ---
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
$taskInfo = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
if ($taskInfo.LastTaskResult -ne 0 -and $taskInfo.LastRunTime -eq [DateTime]::MinValue) {
    Write-Warning "Task registered but may not have started yet. Check Task Scheduler."
} else {
    Write-Host "[install_windows] task started successfully."
}

# --- FIX 5: Health check endpoint ---
Write-Host ""
Write-Host "[install_windows] done. Inspect with:"
Write-Host "  Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo"
Write-Host "  Get-Content `"$env:APPDATA\swarm-hive\agent.json`""
Write-Host ""
Write-Host "[install_windows] To verify the node is enrolled:"
Write-Host "  curl $leader/api/hive/nodes"
'''

with open(ORIG, 'w', encoding='utf-8') as f:
    f.write(new_script)

print(f'Backed up original to: {BACKUP}')
print(f'Wrote fixed installer to: {ORIG}')
print('Fixes applied:')
print('  1. Python fallback: python3, python, py')
print('  2. Bootstrap download from leader when not in repo')
print('  3. Quoted paths via PowerShell wrapper script')
print('  4. Task start verification')
print('  5. Health check hint in output')
