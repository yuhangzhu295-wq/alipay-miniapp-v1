param()

$ErrorActionPreference = "SilentlyContinue"
$Base = "C:\apps\id-photo"
$Shared = Join-Path $Base "shared"
$Logs = Join-Path $Shared "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = Join-Path $Logs "watchdog.log"

function Log($Message) {
  Add-Content -Path $Log -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date).ToString("o"), $Message)
}

function Test-Url($Url) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
    return ($r.StatusCode -eq 200)
  } catch {
    return $false
  }
}

function Start-Task($Name) {
  & schtasks.exe /Run /TN $Name | Out-Null
  if ($LASTEXITCODE -ne 0) { Log "failed to start scheduled task $Name exitCode=$LASTEXITCODE" }
}

if (-not (Test-Url "http://127.0.0.1:8081/api/v1/model")) {
  Log "iopaint unhealthy; starting scheduled task"
  Start-Task "id-photo-iopaint"
}

if (-not (Test-Url "http://127.0.0.1:8000/api/health")) {
  Log "api unhealthy; starting scheduled task"
  Start-Task "id-photo-api"
}

$nginxRunning = Get-Process nginx -ErrorAction SilentlyContinue
if (-not $nginxRunning) {
  Log "nginx not running; starting scheduled task"
  Start-Task "id-photo-nginx"
}
