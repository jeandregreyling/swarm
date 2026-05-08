# bootstrap.ps1 — one-liner installer for a Swarm Hive node on Windows.
#
# Usage (PowerShell):
#   $env:SWARM_HIVE_LEADER = "http://<leader>:5050"
#   irm $env:SWARM_HIVE_LEADER/api/hive/install/bootstrap.ps1 | iex
#
# Optional env: SWARM_HIVE_LEADER, SWARM_NODE_ID, SWARM_HIVE_INTERVAL, SWARM_HIVE_PYTHON

$ErrorActionPreference = "Stop"

$leader = if ($env:SWARM_HIVE_LEADER) { $env:SWARM_HIVE_LEADER.TrimEnd('/') } else { "http://localhost:5050" }
$py     = if ($env:SWARM_HIVE_PYTHON) { $env:SWARM_HIVE_PYTHON } else { "python" }

# Verify python on PATH
try { & $py --version | Out-Null } catch {
    Write-Error "python interpreter '$py' not found on PATH"
    exit 3
}

$stageDir = if ($env:SWARM_HIVE_STAGE) { $env:SWARM_HIVE_STAGE } else { Join-Path $env:LOCALAPPDATA "swarm-hive" }
$opsDir   = Join-Path $stageDir "ops"
$instDir  = Join-Path $opsDir "install"
New-Item -ItemType Directory -Force -Path $instDir | Out-Null

Write-Host "[bootstrap] leader=$leader stage=$stageDir"

Invoke-WebRequest -UseBasicParsing -Uri "$leader/api/hive/install/agent.py" `
    -OutFile (Join-Path $opsDir "hive_agent.py")
Invoke-WebRequest -UseBasicParsing -Uri "$leader/api/hive/install/install_windows.ps1" `
    -OutFile (Join-Path $instDir "install_windows.ps1")

$env:SWARM_HIVE_LEADER = $leader
$env:SWARM_HIVE_PYTHON = $py
& (Join-Path $instDir "install_windows.ps1")

Write-Host ""
Write-Host "[bootstrap] done. Files staged under $stageDir"
