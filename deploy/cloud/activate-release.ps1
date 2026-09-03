param(
  [Parameter(Mandatory = $true)][string]$RunId
)

$ErrorActionPreference = "Stop"
$Base = "C:\apps\id-photo"
$Release = Join-Path $Base "releases\$RunId"
$Current = Join-Path $Base "current"
$Previous = Join-Path $Base "previous"
$Shared = Join-Path $Base "shared"
$Logs = Join-Path $Shared "logs"

function Ensure-Junction($Link, $Target) {
  if (Test-Path $Link) { Remove-Item -Path $Link -Force -Recurse }
  cmd.exe /c mklink /J $Link $Target | Out-Null
}

function Get-ScheduledTasksCompatibility {
  $command = Get-Command New-ScheduledTaskSettingsSet -ErrorAction SilentlyContinue
  $parameterNames = @("AllowStartIfOnBatteries", "DisallowStartIfOnBatteries", "ExecutionTimeLimit", "RestartCount", "RestartInterval")
  $support = [ordered]@{
    newScheduledTaskSettingsSetAvailable = [bool]$command
    parameters = [ordered]@{}
  }
  foreach ($parameterName in $parameterNames) {
    $support.parameters[$parameterName] = ($command -and $command.Parameters.ContainsKey($parameterName))
  }
  return $support
}

function Invoke-Schtasks([string[]]$Arguments, [switch]$AllowFailure) {
  $stdout = Join-Path $Logs ("schtasks-{0}.out.tmp" -f ([guid]::NewGuid().ToString("N")))
  $stderr = Join-Path $Logs ("schtasks-{0}.err.tmp" -f ([guid]::NewGuid().ToString("N")))
  try {
    $schtasksExe = Join-Path $env:SystemRoot "System32\schtasks.exe"
    $previousErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "Continue"
      & $schtasksExe @Arguments 1> $stdout 2> $stderr
      $exitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $previousErrorActionPreference
    }
    $out = if (Test-Path $stdout) { (Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue) } else { "" }
    $err = if (Test-Path $stderr) { (Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue) } else { "" }
    $outText = if ($null -eq $out) { "" } else { [string]$out }
    $errText = if ($null -eq $err) { "" } else { [string]$err }
    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
      throw ("schtasks.exe failed exitCode={0} args={1} stdout={2} stderr={3}" -f $exitCode, ($Arguments -join " "), $outText.Trim(), $errText.Trim())
    }
    return [ordered]@{
      exitCode = $exitCode
      stdout = $outText.Trim()
      stderr = $errText.Trim()
    }
  } finally {
    Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
  }
}

function Test-SchtaskExists($Name) {
  $result = Invoke-Schtasks -Arguments @("/Query", "/TN", $Name) -AllowFailure
  return ($result.exitCode -eq 0)
}

function Remove-SchtaskIfExists($Name) {
  if (Test-SchtaskExists $Name) {
    Invoke-Schtasks -Arguments @("/Delete", "/TN", $Name, "/F") | Out-Null
  }
}

function Register-Schtask($Name, $TaskCommand, [string[]]$ScheduleArgs) {
  Remove-SchtaskIfExists $Name
  $createArgs = @("/Create", "/TN", $Name, "/RU", "SYSTEM", "/RL", "HIGHEST", "/TR", $TaskCommand, "/F") + $ScheduleArgs
  Invoke-Schtasks -Arguments $createArgs | Out-Null
  if (-not (Test-SchtaskExists $Name)) { throw "scheduled task was not found after registration: $Name" }
  return [ordered]@{
    name = $Name
    exists = $true
    schedule = ($ScheduleArgs -join " ")
  }
}

function Start-Schtask($Name, [switch]$Optional) {
  $result = Invoke-Schtasks -Arguments @("/Run", "/TN", $Name) -AllowFailure:$Optional
  if (($result.exitCode -ne 0) -and (-not $Optional)) {
    throw ("failed to start scheduled task: {0} stdout={1} stderr={2}" -f $Name, $result.stdout, $result.stderr)
  }
  return [ordered]@{
    name = $Name
    requested = ($result.exitCode -eq 0)
    optional = [bool]$Optional
    stdout = $result.stdout
    stderr = $result.stderr
  }
}

if (-not (Test-Path $Release)) { throw "Release not found: $Release" }
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

$ValidationPort = 18000
$ValidationOut = Join-Path $Logs "pre-activate-$RunId.out.log"
$ValidationErr = Join-Path $Logs "pre-activate-$RunId.err.log"
$Python = Join-Path $Release ".venv\Scripts\python.exe"
$env:ID_PHOTO_RUNTIME_DIR = $Shared
$env:ID_PHOTO_ASSET_RETENTION_SECONDS = "86400"
$env:IOPAINT_URL = "http://127.0.0.1:8081"
$proc = Start-Process -FilePath $Python -ArgumentList @("-m","uvicorn","main:app","--host","127.0.0.1","--port",[string]$ValidationPort) -WorkingDirectory (Join-Path $Release "server") -RedirectStandardOutput $ValidationOut -RedirectStandardError $ValidationErr -PassThru
try {
  $ok = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 2
    try {
      $r = Invoke-RestMethod -Uri "http://127.0.0.1:$ValidationPort/api/health" -TimeoutSec 5
      if ($r.success -eq $true) { $ok = $true; break }
    } catch {}
  }
  if (-not $ok) { throw "pre-activation health check failed" }
} finally {
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

$PreviousTarget = $null
if (Test-Path $Current) {
  $item = Get-Item $Current -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    $target = $item.Target
    if ($target) {
      $PreviousTarget = $target
      Ensure-Junction $Previous $target
    }
  }
}
Ensure-Junction $Current $Release

$ScheduledTasksCompatibility = Get-ScheduledTasksCompatibility
$Ps = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File"
$RequiredTasks = @("id-photo-api", "id-photo-nginx", "id-photo-watchdog", "id-photo-cleanup-24h")
$TaskResults = @()
$TaskResults += Register-Schtask "id-photo-iopaint" "$Ps `"$Current\deploy\cloud\start-iopaint.ps1`"" @("/SC", "ONSTART")
$TaskResults += Register-Schtask "id-photo-api" "$Ps `"$Current\deploy\cloud\start-id-photo.ps1`" -Port 8000" @("/SC", "ONSTART")
$TaskResults += Register-Schtask "id-photo-nginx" "$Ps `"$Current\deploy\cloud\start-nginx.ps1`"" @("/SC", "ONSTART")
$TaskResults += Register-Schtask "id-photo-watchdog" "$Ps `"$Current\deploy\cloud\watchdog.ps1`"" @("/SC", "MINUTE", "/MO", "1")
$TaskResults += Register-Schtask "id-photo-cleanup-24h" "$Ps `"$Current\deploy\cloud\cleanup-assets.ps1`"" @("/SC", "HOURLY", "/MO", "1")
$TaskVerification = foreach ($taskName in (@("id-photo-iopaint") + $RequiredTasks)) {
  [ordered]@{
    name = $taskName
    exists = (Test-SchtaskExists $taskName)
    required = ($RequiredTasks -contains $taskName)
  }
}

try {
  New-NetFirewallRule -DisplayName "id-photo-http-80" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 -ErrorAction SilentlyContinue | Out-Null
} catch {}

$StartResults = @()
$StartResults += Start-Schtask "id-photo-nginx"
$StartResults += Start-Schtask "id-photo-iopaint" -Optional
Start-Sleep -Seconds 5
$StartResults += Start-Schtask "id-photo-api"
$StartResults += Start-Schtask "id-photo-watchdog"
$StartResults += Start-Schtask "id-photo-cleanup-24h"

$Health = [ordered]@{
  api = $false
  iopaint = $false
  iopaintStatus = "not_checked"
}
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 5
    if ($r.success -eq $true) { $Health.api = $true; break }
  } catch {}
}
try {
  $iopaintProbe = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8081/api/v1/model" -TimeoutSec 5
  $Health.iopaint = ($iopaintProbe.StatusCode -eq 200)
  $Health.iopaintStatus = if ($Health.iopaint) { "healthy" } else { "unavailable" }
} catch {
  $Health.iopaint = $false
  $Health.iopaintStatus = "unavailable_or_starting"
}
if (-not $Health.api) { throw "api health check failed after activation" }

$Result = [ordered]@{
  runId = $RunId
  current = $Release
  currentLink = $Current
  previous = $PreviousTarget
  previousLink = $Previous
  activatedAt = (Get-Date).ToString("o")
  taskRegistrationMethod = "schtasks.exe"
  scheduledTasksCompatibility = $ScheduledTasksCompatibility
  taskRegistration = $TaskResults
  taskVerification = $TaskVerification
  taskStart = $StartResults
  health = $Health
}
$Result | ConvertTo-Json -Depth 8 | Tee-Object -FilePath (Join-Path $Logs "activate-$RunId.json")
