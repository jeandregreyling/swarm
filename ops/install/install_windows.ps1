# install_windows.ps1 — install the Swarm Hive agent as a per-user
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
$py       = if ($env:SWARM_HIVE_PYTHON)   { $env:SWARM_HIVE_PYTHON }   else { "python" }

$repoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$agent    = Join-Path $repoRoot "ops\hive_agent.py"

if (-not (Test-Path $agent)) {
    Write-Error "agent not found at $agent"
    exit 2
}

# Quick sanity: python on PATH?
try {
    & $py --version | Out-Null
} catch {
    Write-Error "python interpreter '$py' not found on PATH"
    exit 3
}

Write-Host "[install_windows] enrolling with leader=$leader ..."
$enrolArgs = @($agent, "--enrol", "--leader", $leader)
if ($nodeId) { $enrolArgs += @("--node-id", $nodeId) }
& $py @enrolArgs

$taskName = "SwarmHiveAgent"
$argLine  = """$agent"" --run --interval $interval"

# Build env block: leader (and optional node id) wired into the action.
# Scheduled tasks don't have direct env support in older PowerShell, so
# wrap the agent in a cmd shell that sets env vars before invoking it.
$cmdArgs = "/c set SWARM_HIVE_LEADER=$leader"
if ($nodeId) { $cmdArgs += " && set SWARM_NODE_ID=$nodeId" }
$cmdArgs += " && ""$py"" $argLine"

$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmdArgs
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 9999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description "Swarm Hive node agent"

Start-ScheduledTask -TaskName $taskName

Write-Host ""
Write-Host "[install_windows] done. Inspect with:"
Write-Host "  Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo"
Write-Host "  Get-Content `"$env:APPDATA\swarm-hive\agent.json`""
