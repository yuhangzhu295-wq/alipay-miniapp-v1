param(
  [int]$Port = 8081,
  [string]$ReleasePath = ""
)

$ErrorActionPreference = "Stop"
$Base = "C:\apps\id-photo"
$Shared = Join-Path $Base "shared"
$Logs = Join-Path $Shared "logs"
if (-not $ReleasePath) { $ReleasePath = Join-Path $Base "current" }
$Python = Join-Path $ReleasePath ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HOME = Join-Path $Shared "models\huggingface"
$env:TORCH_HOME = Join-Path $Shared "models\torch"
New-Item -ItemType Directory -Force -Path $env:HF_HOME, $env:TORCH_HOME | Out-Null

function Write-Log($Message) {
  Add-Content -Path (Join-Path $Logs "iopaint-supervisor.log") -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date).ToString("o"), $Message)
}

function Test-Iopaint() {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/v1/model" -TimeoutSec 5
    return ($r.StatusCode -eq 200)
  } catch {
    return $false
  }
}

if (Test-Iopaint) {
  Write-Log "iopaint already healthy on port $Port"
  exit 0
}

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*iopaint*start*--port*$Port*" }
if ($existing) {
  Write-Log "iopaint process already starting pid=$($existing.ProcessId)"
  exit 0
}

$OutLog = Join-Path $Logs "iopaint.log"
$ErrLog = Join-Path $Logs "iopaint.err.log"
$proc = Start-Process -FilePath $Python -ArgumentList @("-m", "iopaint", "start", "--model", "lama", "--device", "cpu", "--host", "127.0.0.1", "--port", [string]$Port) -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -PassThru
Write-Log "iopaint start requested pid=$($proc.Id) port=$Port"

for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Iopaint) { Write-Log "iopaint healthy pid=$($proc.Id) port=$Port"; exit 0 }
  if ($proc.HasExited) {
    $tail = ""
    if (Test-Path $ErrLog) { $tail = (Get-Content -Tail 30 -LiteralPath $ErrLog) -join "`n" }
    throw "iopaint process exited code=$($proc.ExitCode) stderr=$tail"
  }
}

Write-Log "iopaint health pending pid=$($proc.Id) port=$Port"
exit 0
