param()

$ErrorActionPreference = "SilentlyContinue"
$Base = "C:\apps\id-photo"
$Shared = Join-Path $Base "shared"
$Logs = Join-Path $Shared "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = Join-Path $Logs "cleanup-assets.log"
$Now = Get-Date

try {
  $r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/assets/cleanup-expired" -TimeoutSec 30
  Add-Content -Path $Log -Encoding UTF8 -Value (($Now.ToString("o")) + " api-cleanup " + ($r | ConvertTo-Json -Compress -Depth 6))
} catch {
  Add-Content -Path $Log -Encoding UTF8 -Value (($Now.ToString("o")) + " api-cleanup-failed " + $_.Exception.Message)
}

$Cutoff = (Get-Date).AddHours(-24)
foreach ($Dir in @("outputs", "uploads", "temp")) {
  $Path = Join-Path $Shared $Dir
  if (Test-Path $Path) {
    Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTime -lt $Cutoff } |
      Remove-Item -Force -ErrorAction SilentlyContinue
  }
}
