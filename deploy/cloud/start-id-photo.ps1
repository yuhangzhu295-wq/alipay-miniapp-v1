param(
  [int]$Port = 8000,
  [string]$ReleasePath = ""
)

$ErrorActionPreference = "Stop"
$Base = "C:\apps\id-photo"
$Shared = Join-Path $Base "shared"
$Logs = Join-Path $Shared "logs"
if (-not $ReleasePath) { $ReleasePath = Join-Path $Base "current" }
$Python = Join-Path $ReleasePath ".venv\Scripts\python.exe"
$Server = Join-Path $ReleasePath "server"

New-Item -ItemType Directory -Force -Path $Logs, (Join-Path $Shared "outputs"), (Join-Path $Shared "uploads"), (Join-Path $Shared "temp") | Out-Null
$env:ID_PHOTO_RUNTIME_DIR = $Shared
$env:ID_PHOTO_ASSET_RETENTION_SECONDS = "86400"
$env:IOPAINT_URL = "http://127.0.0.1:8081"
$env:ENABLE_HD_REPAIR = "true"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Write-Log($Message) {
  Add-Content -Path (Join-Path $Logs "id-photo-api-supervisor.log") -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date).ToString("o"), $Message)
}

function Test-Health() {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 5
    return ($r.success -eq $true)
  } catch {
    return $false
  }
}

if (Test-Health) {
  Write-Log "api already healthy on port $Port"
  exit 0
}

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*uvicorn*main:app*--port*$Port*" }
if ($existing) {
  Write-Log "api process already starting pid=$($existing.ProcessId)"
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Health) { Write-Log "api became healthy on port $Port"; exit 0 }
  }
  Write-Log "api process exists but health is still pending"
  exit 0
}

$OutLog = Join-Path $Logs "id-photo-api.log"
$ErrLog = Join-Path $Logs "id-photo-api.err.log"
$proc = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", [string]$Port) -WorkingDirectory $Server -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -PassThru
Write-Log "api start requested pid=$($proc.Id) port=$Port"

for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Health) { Write-Log "api healthy pid=$($proc.Id) port=$Port"; exit 0 }
  if ($proc.HasExited) {
    $tail = ""
    if (Test-Path $ErrLog) { $tail = (Get-Content -Tail 20 -LiteralPath $ErrLog) -join "`n" }
    throw "api process exited code=$($proc.ExitCode) stderr=$tail"
  }
}

Write-Log "api health pending pid=$($proc.Id) port=$Port"
exit 0
